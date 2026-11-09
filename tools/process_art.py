#!/usr/bin/env python3
"""
Sprite-sheet art pipeline.

Reads the hand-labelled AI output in art/raw/<character>/ (READ-ONLY) and produces
game-ready sheets in art/sheets/<character>/ plus a cropped portrait in
art/portraits/<character>.png.

For each character:
  1. Keys out the magenta background by colour distance (not exact match) and
     neutralises the pink halo on anti-aliased fringe pixels.
  2. Splits each sheet into figures by scanning for runs of empty columns.
  3. Measures EVERY figure in ALL four sheets before placing any of them, then
     derives ONE cell size shared by the whole character, so the character never
     resizes when the game switches animation.
  4. Rebuilds each sheet on that grid: every figure sits at the same anchor
     column and on a common baseline, so it never jitters between states.

The four sheets are generated independently and come back drawn at noticeably
different sizes, so before any of that the pipeline measures the character's
head on every sheet and rescales the sheets to agree. Without it the character
changes size when the game switches animation, which no amount of careful
placement can fix.

Usage:
    python tools/process_art.py                  # process every character
    python tools/process_art.py --only Sara Jo   # process a subset
    python tools/process_art.py --scale 0.5      # nearest-neighbour downscale
    python tools/process_art.py --symmetric      # anchor at the exact cell centre
    python tools/process_art.py --no-normalize  # keep each sheet's original scale

Head normalisation is measured automatically; art/scale_overrides.json can nudge
any sheet that still looks off, e.g. {"Pedro": {"attack": 0.88}}.
    python tools/process_art.py --report art/report.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field

import numpy as np
from PIL import Image
from scipy import ndimage

RAW_DIR = "art/raw"          # never written to
OVERRIDES = "art/scale_overrides.json"   # optional hand nudges, see head_scales()
SHEET_DIR = "art/sheets"
PORTRAIT_DIR = "art/portraits"

# Expected animations and frame counts. The baby character crawls instead of
# running, but the frame count is unchanged.
ANIMS = {"idle": 4, "run": 6, "jump": 6, "attack": 5}
PORTRAIT_KEY = "front"

# --- keying ------------------------------------------------------------------
# The background is magenta at a *range* of brightnesses: the AI output has a
# vignette, and the figures cast dark-magenta ground shadows. So the background
# is modelled as a ray through RGB space (magenta at any brightness) rather than
# a single colour, and gated on distance-from-ray plus brightness-along-ray.
# A plain distance-to-#FF00FF threshold cannot separate a dark magenta shadow
# (keep out) from a dark grey garment fold (keep in); this can.
PERP_TOL = 50.0        # max distance from the magenta ray to count as background-ish
K_LOW = 0.30           # min brightness along the ray; below this it is content (black outline)
K_HI = 1.35            # sanity ceiling
SPILL_FRAC = 0.12      # magenta cast, as a fraction of the background's own cast, above which
                       # an off-ray pixel is treated as partial coverage rather than solid art
FRINGE_RADIUS = 2      # magenta-ish pixels this close to solid content are fringe, not background
FOREGROUND_RADIUS = 3  # neighbourhood used to estimate the true colour behind a fringe pixel
ALPHA_FLOOR = 0.04     # below this a fringe pixel is dropped outright
DESPECKLE = 4          # drop solid components smaller than this many pixels

SOLID_ALPHA = 0.5      # alpha at which a pixel counts as structural (segmentation)
ANY_ALPHA = 0.02       # alpha above which a pixel must not be clipped
FEET_BAND = 0.25       # bottom fraction of a figure used to locate its feet
PAD = 2                # transparent margin inside each cell


# =============================================================================
# Keying
# =============================================================================

def estimate_background(a: np.ndarray) -> np.ndarray:
    """Estimate the background colour from the border, then refine it in-place."""
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = np.median(border, axis=0)
    for _ in range(2):
        norm = float(np.linalg.norm(bg))
        if norm < 1e-6:
            break
        u = bg / norm
        proj = a @ u
        perp = np.linalg.norm(a - proj[..., None] * u, axis=2)
        k = proj / norm
        sel = (perp < 40) & (k > 0.85) & (k < K_HI)
        if sel.sum() < 1000:
            break
        bg = np.median(a[sel], axis=0)
    return bg


def key_image(a: np.ndarray, bg: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """Split an RGB image into de-fringed RGB plus a float alpha in [0, 1]."""
    norm = float(np.linalg.norm(bg))
    u = bg / norm
    proj = a @ u
    perp = np.linalg.norm(a - proj[..., None] * u, axis=2)
    k = proj / norm

    # Pixels lying ON the magenta ray are background at some brightness: the flat
    # field, the vignette, and the dark magenta ground shadows all land here.
    on_ray = (perp < PERP_TOL) & (k > K_LOW) & (k < K_HI)
    solid = ~on_ray

    # Off-ray pixels can still be *partly* background. The AI drew the attack
    # streaks as translucent orange over the magenta, so those pixels have enough
    # green to leave the ray while still being mostly background -- keeping them
    # opaque is what produces bright pink dashes. Split them off by how much
    # magenta cast they carry relative to the background's own.
    spill = np.minimum(a[..., 0], a[..., 2]) - a[..., 1]
    spill_bg = float(min(bg[0], bg[2]) - bg[1])
    core = solid & (spill <= SPILL_FRAC * spill_bg)
    mixed = solid & ~core

    speckles = 0
    if DESPECKLE > 0:
        lab, n = ndimage.label(core, structure=np.ones((3, 3), bool))
        if n:
            sizes = np.bincount(lab.ravel())
            small = np.flatnonzero(sizes < DESPECKLE)
            if small.size:
                drop = np.isin(lab, small) & core
                speckles = int(drop.sum())
                core &= ~drop

    alpha = core.astype(np.float64)

    # Fringe = on-ray pixels hugging solid content: the anti-aliased edge pixels
    # that carry the pink halo.
    near = ndimage.binary_dilation(
        core, ndimage.generate_binary_structure(2, 2), iterations=FRINGE_RADIUS
    )
    unknown = (on_ray & near) | mixed

    if unknown.any():
        # Estimate the true colour behind each uncertain pixel from the CORE
        # pixels around it -- averaging over the uncertain ones too would poison
        # the estimate with the very pink we are trying to remove. Then solve
        # C = alpha*F + (1-alpha)*BG for alpha by projecting C-BG onto F-BG.
        size = 2 * FOREGROUND_RADIUS + 1
        w = ndimage.uniform_filter(core.astype(np.float64), size=size)
        f = np.stack(
            [ndimage.uniform_filter(a[..., i] * core, size=size) for i in range(3)],
            axis=-1,
        ) / np.maximum(w, 1e-9)[..., None]

        # Where no core pixel is in reach, fall back to the nearest one.
        blind = w < 0.02
        if blind.any() and core.any():
            _, idx = ndimage.distance_transform_edt(~core, return_indices=True)
            f = np.where(blind[..., None], a[idx[0], idx[1]], f)

        df = f - bg
        dc = a - bg
        denom = (df * df).sum(-1)
        al = np.where(denom > 1e-6, (dc * df).sum(-1) / np.maximum(denom, 1e-6), 0.0)
        alpha = np.where(unknown, np.clip(al, 0.0, 1.0), alpha)

    alpha = np.where(alpha < ALPHA_FLOOR, 0.0, alpha)

    # Un-premultiply: recover the foreground with the magenta removed. This is
    # what actually kills the halo -- a fringe pixel keeps its coverage via alpha
    # but loses its pink tint.
    m = alpha > 0
    recovered = bg + (a - bg) / np.maximum(alpha, 1e-6)[..., None]
    out = np.clip(np.where(m[..., None], recovered, a), 0, 255)

    # Final despill. Un-premultiplying with a slightly over-estimated alpha
    # leaves a 1px dark-purple rim on some outlines. Any *output* pixel still
    # sitting on the magenta ray is residue by definition -- no character wears
    # magenta -- so pull its red and blue down to its green. The test is relative
    # to brightness so dark reds and maroons are left alone.
    o_proj = out @ u
    o_perp = np.linalg.norm(out - o_proj[..., None] * u, axis=2)
    residue = m & (o_perp < 0.20 * np.maximum(o_proj, 1.0)) & (o_proj / norm > 0.02)
    if residue.any():
        excess = np.maximum(np.minimum(out[..., 0], out[..., 2]) - out[..., 1], 0.0)
        out[..., 0] = np.where(residue, out[..., 0] - excess, out[..., 0])
        out[..., 2] = np.where(residue, out[..., 2] - excess, out[..., 2])
        out = np.clip(out, 0, 255)

    return out, alpha, {
        "bg": [round(float(v), 1) for v in bg],
        "fringe_px": int((on_ray & near).sum()),
        "partial_px": int(mixed.sum()),
        "speckles_removed": speckles,
    }


def load_keyed(path: str) -> tuple[np.ndarray, np.ndarray, dict]:
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.float64)
    return key_image(a, estimate_background(a))


# =============================================================================
# Segmentation
# =============================================================================

def find_cuts(col_energy: np.ndarray, n: int) -> tuple[list[int], list[float]]:
    """Find the n-1 frame boundaries by scanning for runs of empty columns.

    Frames sit on a roughly regular pitch, so we take the widest empty run near
    each nominal boundary. That reproduces plain gap-scanning wherever the gaps
    are clean, and still lands sensibly on attack sheets, where a thrown orb and
    its motion dashes fill the gap between two frames.
    """
    w = len(col_energy)
    pitch = w / n
    cuts: list[int] = []
    crossed: list[float] = []
    for i in range(1, n):
        ideal = pitch * i
        lo = int(max(1, ideal - 0.42 * pitch))
        hi = int(min(w - 1, ideal + 0.42 * pitch))
        xs = np.arange(lo, hi)
        win = col_energy[lo:hi]
        empty = xs[win <= 0]
        if empty.size:
            runs = []
            start = prev = empty[0]
            for x in empty[1:]:
                if x != prev + 1:
                    runs.append((start, prev))
                    start = x
                prev = x
            runs.append((start, prev))
            best = max(runs, key=lambda r: (r[1] - r[0]) - abs((r[0] + r[1]) / 2 - ideal) / pitch)
            cut = int((best[0] + best[1]) // 2)
        else:
            cut = int(xs[np.argmin(win)])
        cuts.append(cut)
        crossed.append(float(col_energy[cut]))
    return cuts, crossed


@dataclass
class Frame:
    index: int
    anchor_x: int    # horizontal centre of the figure's feet, in sheet coords
    baseline_y: int  # lowest row of the main figure, in sheet coords
    cx0: int         # bbox of ALL content owned by this frame (thrown orbs included)
    cy0: int
    cx1: int
    cy1: int
    fig_w: int
    fig_h: int
    extra_blobs: int  # detached pieces owned by this frame (orb, motion dashes)


@dataclass
class SheetData:
    anim: str
    rgb: np.ndarray
    alpha: np.ndarray
    owner: np.ndarray  # frame index per pixel, -1 where empty
    frames: list[Frame]
    cuts: list[int]
    crossed: list[float]
    diag: dict
    raw_blobs: int
    sliced: int


def segment_sheet(alpha: np.ndarray, n: int) -> tuple[np.ndarray, list[Frame], list[int], list[float], int, int]:
    """Cut a sheet into n frames and assign every pixel to exactly one frame.

    Figures are separated as whole connected components rather than by slicing
    the image at the cut column: on attack sheets a figure's outstretched arm can
    overlap the next figure's column range without ever touching it, so slicing
    would shear a limb or an orb in half.
    """
    solid = alpha >= SOLID_ALPHA
    lab, ncomp = ndimage.label(solid, structure=np.ones((3, 3), bool))
    if ncomp == 0:
        raise RuntimeError("sheet is empty")

    col = solid.sum(axis=0)
    occ = col > 0
    raw_blobs = int(np.sum(occ[1:] & ~occ[:-1])) + (1 if occ[0] else 0)

    cuts, crossed = find_cuts(col, n)
    sliced = int(sum(1 for c in crossed if c > 0))

    # Assign each component wholly to the frame containing its centroid.
    coms = ndimage.center_of_mass(solid, lab, range(1, ncomp + 1))
    comp_cx = np.array([c[1] for c in coms])
    comp_frame = np.digitize(comp_cx, cuts)  # 0 .. n-1

    sizes = np.bincount(lab.ravel(), minlength=ncomp + 1)
    sizes[0] = 0

    # Every partially transparent fringe pixel belongs to its nearest component.
    _, idx = ndimage.distance_transform_edt(lab == 0, return_indices=True)
    owner_comp = lab[idx[0], idx[1]]
    comp_to_frame = np.empty(ncomp + 1, np.int64)
    comp_to_frame[0] = -1
    comp_to_frame[1:] = comp_frame
    owner = np.where(alpha >= ANY_ALPHA, comp_to_frame[owner_comp], -1)

    frames: list[Frame] = []
    for i in range(n):
        members = np.flatnonzero(comp_frame == i) + 1
        if members.size == 0:
            raise RuntimeError(f"frame {i} has no figure")
        main = int(members[np.argmax(sizes[members])])

        ys, xs = np.where(lab == main)
        fy0, fy1 = int(ys.min()), int(ys.max())
        fx0, fx1 = int(xs.min()), int(xs.max())

        # Centre on the feet, not the bounding box: an outstretched arm or a
        # charged orb must not drag the character sideways between frames.
        band_top = fy1 - max(0, int(round((fy1 - fy0 + 1) * FEET_BAND)) - 1)
        feet_cols = np.where((lab[band_top:fy1 + 1] == main).any(axis=0))[0]
        anchor_x = int((feet_cols.min() + feet_cols.max()) // 2) if feet_cols.size else (fx0 + fx1) // 2

        cys, cxs = np.where(owner == i)
        frames.append(Frame(
            index=i,
            anchor_x=anchor_x,
            baseline_y=fy1,
            cx0=int(cxs.min()), cy0=int(cys.min()),
            cx1=int(cxs.max()), cy1=int(cys.max()),
            fig_w=fx1 - fx0 + 1, fig_h=fy1 - fy0 + 1,
            extra_blobs=int(members.size) - 1,
        ))
    return owner, frames, cuts, crossed, raw_blobs, sliced


def load_sheet(char: str, anim: str) -> SheetData:
    rgb, alpha, diag = load_keyed(f"{RAW_DIR}/{char}/{anim}.png")
    owner, frames, cuts, crossed, raw_blobs, sliced = segment_sheet(alpha, ANIMS[anim])
    return SheetData(anim, rgb, alpha, owner, frames, cuts, crossed, diag, raw_blobs, sliced)


# =============================================================================
# Head measurement and scale normalisation
# =============================================================================
# The four sheets of a character were generated independently and are drawn at
# noticeably different sizes -- Jo's running head is about half the size of her
# standing one. Nothing downstream can fix that, so we measure the head on every
# sheet and rescale the sheets to agree before any placement happens.
#
# Two independent measures are used because each fails differently: the visible
# face shrinks when a raised arm crosses it, and the eye is not always detected.
# They are combined only when both are available for all four sheets.

ST8 = np.ones((3, 3), bool)
SKIN_CLOSE = 10   # closes gaps where a brow or hair strand splits the face


def _skin(rgb: np.ndarray) -> np.ndarray:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    # Cartoon skin sits in a tight band; the B/G ratio is what separates it from
    # blonde hair, which is otherwise also R>G>B.
    return (r > 195) & (g > 0.60 * r) & (g < 0.88 * r) & (b > 0.50 * g) & (b < 0.78 * g)


def head_metrics(rgb: np.ndarray, alpha: np.ndarray, owner: np.ndarray,
                 f: Frame) -> tuple[float | None, float | None]:
    """Return (face height, eye height) for one frame, either may be None."""
    sl = (slice(f.cy0, f.cy1 + 1), slice(f.cx0, f.cx1 + 1))
    m = (owner[sl] == f.index) & (alpha[sl] >= SOLID_ALPHA)
    if not m.any():
        return None, None
    sub = rgb[sl]
    ys, _ = np.where(m)
    y0, y1 = int(ys.min()), int(ys.max())
    h = y1 - y0 + 1
    band = np.zeros_like(m)
    band[y0:y0 + int(h * 0.55)] = True

    skin = _skin(sub) & m & band
    # Close before labelling: an eyebrow or a strand of hair crossing the cheek
    # splits the skin into pieces, and measuring only the largest piece makes the
    # face read far too small on some frames (Pedro's attack swung 62-97px).
    face = None
    closed = ndimage.binary_closing(skin, ST8, iterations=SKIN_CLOSE) & m
    if closed.sum() >= 200:
        lab, _ = ndimage.label(closed, structure=ST8)
        sizes = np.bincount(lab.ravel())
        sizes[0] = 0
        fy, _ = np.where(lab == int(np.argmax(sizes)))
        face = float(fy.max() - fy.min() + 1)

    eye = None
    white = (sub.min(-1) > 185) & m & band
    lab, n = ndimage.label(white, structure=ST8)
    for i in range(1, n + 1):
        blob = lab == i
        if blob.sum() < 40:
            continue
        ring = ndimage.binary_dilation(blob, ST8, iterations=3) & ~blob
        if not ring.any():
            continue
        # A sclera sits in skin and abuts a dark pupil; an energy orb does neither.
        if (skin & ring).sum() / ring.sum() < 0.30:
            continue
        if not ((sub.max(-1) < 80) & ring).any():
            continue
        yy, xx = np.where(blob)
        hh, ww = yy.max() - yy.min() + 1, xx.max() - xx.min() + 1
        if 0.4 < hh / ww < 3.5:
            eye = max(eye or 0.0, float(hh))
    return face, eye


def sheet_head(sd: SheetData) -> tuple[float | None, float | None]:
    """Median face height for the sheet, plus the eye height as a cross-check.

    Only the face drives normalisation. Measured against the resulting standing
    heights, face-median was the most accurate of the variants tried (worst
    character off by 15%, versus 25-28% when the eye measure was mixed in): the
    eye is small enough that a pixel or two of detection error is a large
    relative error.
    """
    faces, eyes = [], []
    for f in sd.frames:
        a, b = head_metrics(sd.rgb, sd.alpha, sd.owner, f)
        if a:
            faces.append(a)
        if b:
            eyes.append(b)
    return (float(np.median(faces)) if faces else None,
            float(np.median(eyes)) if eyes else None)


def head_scales(sheets: dict, char: str = "") -> tuple[dict, dict]:
    """Per-sheet rescale factors that bring every sheet to a common head size."""
    heads = {a: sheet_head(sd) for a, sd in sheets.items()}
    faces = {a: h[0] for a, h in heads.items()}
    eyes = {a: h[1] for a, h in heads.items()}

    def rel(vals):
        if any(v is None for v in vals.values()):
            return None
        gm = float(np.exp(np.mean(np.log(list(vals.values())))))
        return {a: v / gm for a, v in vals.items()}

    rel_size = rel(faces)
    if rel_size is None:
        return {a: 1.0 for a in sheets}, heads

    # Target the smallest head so every factor is <= 1 and nothing is upscaled.
    target = min(rel_size.values())
    out = {a: target / rel_size[a] for a in sheets}

    # Measurement cannot get every sheet right: on Pedro's attack the head turns
    # away mid-throw so the face reads small, while on Olimpia's it merges with a
    # raised arm and reads large -- no single statistic fixes both. Whatever is
    # left over is a judgement call, so allow a hand nudge per character/sheet.
    if char and os.path.exists(OVERRIDES):
        with open(OVERRIDES) as fh:
            ov = json.load(fh).get(char, {})
        for a, mult in ov.items():
            if a in out:
                out[a] *= float(mult)
    return out, heads


def rescale_sheet(sd: SheetData, factor: float, n: int) -> SheetData:
    """Resize a keyed sheet and re-derive its frames on the new geometry."""
    h, w = sd.alpha.shape
    nw, nh = max(1, round(w * factor)), max(1, round(h * factor))

    # Resample premultiplied, or colour bleeds out of the transparent regions.
    pm = np.concatenate([sd.rgb * sd.alpha[..., None], sd.alpha[..., None] * 255.0], axis=-1)
    im = Image.fromarray(np.clip(np.round(pm), 0, 255).astype(np.uint8), "RGBA") \
        .resize((nw, nh), Image.LANCZOS)
    arr = np.asarray(im).astype(np.float64)
    alpha = arr[..., 3] / 255.0
    rgb = np.where(alpha[..., None] > 1e-6, arr[..., :3] / np.maximum(alpha, 1e-6)[..., None], 0.0)
    rgb = np.clip(rgb, 0, 255)

    owner, frames, cuts, crossed, raw_blobs, sliced = segment_sheet(alpha, n)
    diag = dict(sd.diag)
    diag["rescaled_by"] = round(factor, 4)
    return SheetData(sd.anim, rgb, alpha, owner, frames, cuts, crossed, diag, raw_blobs, sliced)


# =============================================================================
# Composition
# =============================================================================

@dataclass
class CharResult:
    name: str
    cell_w: int
    cell_h: int
    anchor_x: int
    baseline_y: int
    portrait: tuple[int, int] = (0, 0)
    sheets: dict = field(default_factory=dict)


def compose_character(char: str, scale: float, symmetric: bool, out_root: str,
                      normalize: bool = True) -> CharResult:
    # --- measure every figure in every sheet BEFORE placing any of them -------
    sheets = {anim: load_sheet(char, anim) for anim in ANIMS}

    # Bring the four sheets to a common head size first, so the "one cell size"
    # below describes a character that is actually one size.
    heads: dict = {}
    factors = {a: 1.0 for a in sheets}
    if normalize:
        factors, heads = head_scales(sheets, char)
        for anim, fac in factors.items():
            if abs(fac - 1.0) > 0.01:
                sheets[anim] = rescale_sheet(sheets[anim], fac, ANIMS[anim])

    left = right = top = below = 0
    for sd in sheets.values():
        for f in sd.frames:
            left = max(left, f.anchor_x - f.cx0)
            right = max(right, f.cx1 - f.anchor_x)
            top = max(top, f.baseline_y - f.cy0)
            below = max(below, f.cy1 - f.baseline_y)

    # ONE cell size for the whole character.
    if symmetric:
        half = max(left, right)
        cell_w, anchor_col = 2 * half + 1 + 2 * PAD, PAD + half
    else:
        cell_w, anchor_col = left + right + 1 + 2 * PAD, PAD + left
    cell_h = top + max(0, below) + 1 + 2 * PAD
    baseline_row = PAD + top

    res = CharResult(char, cell_w, cell_h, anchor_col, baseline_row)

    # Derive the scaled cell once and resize every sheet to an exact multiple of
    # it. Scaling each sheet's full width independently would round to something
    # that is not a whole number of cells.
    out_cw = max(1, round(cell_w * scale)) if scale != 1.0 else cell_w
    out_ch = max(1, round(cell_h * scale)) if scale != 1.0 else cell_h

    os.makedirs(f"{out_root}/{SHEET_DIR}/{char}", exist_ok=True)
    for anim, sd in sheets.items():
        n = len(sd.frames)
        canvas = np.zeros((cell_h, cell_w * n, 4), np.float64)
        for f in sd.frames:
            ox = f.index * cell_w + anchor_col - f.anchor_x
            oy = baseline_row - f.baseline_y
            sel = sd.owner[f.cy0:f.cy1 + 1, f.cx0:f.cx1 + 1] == f.index
            src_rgb = sd.rgb[f.cy0:f.cy1 + 1, f.cx0:f.cx1 + 1]
            src_a = sd.alpha[f.cy0:f.cy1 + 1, f.cx0:f.cx1 + 1] * sel
            ys, ye = f.cy0 + oy, f.cy1 + oy + 1
            xs, xe = f.cx0 + ox, f.cx1 + ox + 1
            dst = canvas[ys:ye, xs:xe]
            dst[..., :3] = np.where(sel[..., None], src_rgb, dst[..., :3])
            dst[..., 3] = src_a * 255.0

        img = Image.fromarray(np.clip(np.round(canvas), 0, 255).astype(np.uint8), "RGBA")
        if scale != 1.0:
            img = img.resize((out_cw * n, out_ch), Image.NEAREST)
        img.save(f"{out_root}/{SHEET_DIR}/{char}/{anim}.png")

        res.sheets[anim] = {
            "frames": n,
            "raw_blobs": sd.raw_blobs,
            "cuts": sd.cuts,
            "cuts_through_content": sd.sliced,
            "rescaled_by": round(factors.get(anim, 1.0), 4),
            "head_face_px": heads.get(anim, (None, None))[0],
            "head_eye_px": heads.get(anim, (None, None))[1],
            "extra_blobs": [f.extra_blobs for f in sd.frames],
            "fig_w": [f.fig_w for f in sd.frames],
            "fig_h": [f.fig_h for f in sd.frames],
            **sd.diag,
        }

    # --- portrait ------------------------------------------------------------
    os.makedirs(f"{out_root}/{PORTRAIT_DIR}", exist_ok=True)
    prgb, palpha, _ = load_keyed(f"{RAW_DIR}/{char}/{PORTRAIT_KEY}.png")
    ys, xs = np.where(palpha >= ANY_ALPHA)
    y0 = max(0, int(ys.min()) - PAD)
    x0 = max(0, int(xs.min()) - PAD)
    y1 = min(palpha.shape[0] - 1, int(ys.max()) + PAD)
    x1 = min(palpha.shape[1] - 1, int(xs.max()) + PAD)
    pc = np.zeros((y1 - y0 + 1, x1 - x0 + 1, 4), np.float64)
    pc[..., :3] = prgb[y0:y1 + 1, x0:x1 + 1]
    pc[..., 3] = palpha[y0:y1 + 1, x0:x1 + 1] * 255.0
    pim = Image.fromarray(np.clip(np.round(pc), 0, 255).astype(np.uint8), "RGBA")
    if scale != 1.0:
        pim = pim.resize((max(1, round(pim.width * scale)),
                          max(1, round(pim.height * scale))), Image.NEAREST)
    pim.save(f"{out_root}/{PORTRAIT_DIR}/{char}.png")
    res.portrait = pim.size

    if scale != 1.0:
        res.cell_w = out_cw
        res.cell_h = out_ch
        # Clamp: rounding can otherwise push the anchor one pixel past the cell.
        res.anchor_x = min(out_cw - 1, round(anchor_col * scale))
        res.baseline_y = min(out_ch - 1, round(baseline_row * scale))
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", nargs="*", default=None, help="process only these characters")
    ap.add_argument("--scale", type=float, default=1.0, help="nearest-neighbour output scale")
    ap.add_argument("--no-normalize", action="store_true",
                    help="skip head-size normalisation across a character's sheets")
    ap.add_argument("--symmetric", action="store_true",
                    help="place the anchor at the exact cell centre (wider cells)")
    ap.add_argument("--out", default=".", help="output root (defaults to the repo root)")
    ap.add_argument("--report", default=None, help="write a JSON diagnostics report here")
    args = ap.parse_args()

    if not os.path.isdir(RAW_DIR):
        print(f"error: {RAW_DIR} not found -- run from the repo root", file=sys.stderr)
        return 1

    chars = sorted(d for d in os.listdir(RAW_DIR) if os.path.isdir(f"{RAW_DIR}/{d}"))
    if args.only:
        chars = [c for c in chars if c in set(args.only)]

    results = [compose_character(c, args.scale, args.symmetric, args.out,
                                 normalize=not args.no_normalize) for c in chars]
    for r in results:
        print(f"{r.name:10} cell {r.cell_w}x{r.cell_h}  anchor x={r.anchor_x} baseline y={r.baseline_y}"
              f"  portrait {r.portrait[0]}x{r.portrait[1]}")
        fac = {a: s["rescaled_by"] for a, s in r.sheets.items()}
        if any(abs(v - 1.0) > 0.01 for v in fac.values()):
            print(f"{'':10} head-normalised: " +
                  "  ".join(f"{a}x{v:.2f}" for a, v in fac.items()))

    manifest = {
        r.name: {
            "cell": [r.cell_w, r.cell_h],
            "anchor": [r.anchor_x, r.baseline_y],
            "animations": {a: s["frames"] for a, s in r.sheets.items()},
            "portrait": list(r.portrait),
            # Largest figure in the idle sheet, in cell pixels. This is the
            # character's true standing size, so anything that needs to show the
            # cast at honest relative sizes (the select screen) can derive it
            # instead of guessing from the portrait crop, which is rendered at
            # an unrelated scale and is not normalised.
            "figure": [max(r.sheets["idle"]["fig_w"]), max(r.sheets["idle"]["fig_h"])],
        } for r in results
    }
    os.makedirs(f"{args.out}/{SHEET_DIR}", exist_ok=True)
    with open(f"{args.out}/{SHEET_DIR}/manifest.json", "w") as fh:
        json.dump(manifest, fh, indent=2)

    if args.report:
        with open(args.report, "w") as fh:
            json.dump([{"name": r.name, "cell_w": r.cell_w, "cell_h": r.cell_h,
                        "anchor_x": r.anchor_x, "baseline_y": r.baseline_y,
                        "portrait": list(r.portrait), "sheets": r.sheets} for r in results],
                      fh, indent=2)
        print(f"report -> {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
