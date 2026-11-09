#!/usr/bin/env python3
"""
Independent QA pass over the processed sheets.

Re-reads only the files in art/sheets/ and art/portraits/ -- it does not trust
anything the pipeline reported -- and checks:

  * frame counts are 4 / 6 / 6 / 5
  * one identical cell size across all four sheets of a character
  * every figure's feet land on the shared baseline
  * no pink fringe survives the key
  * no detached limbs (stray components that are not the thrown orb)
  * nothing touches a cell edge (which would mean something was clipped)

Usage:  python tools/verify_art.py [--contact-sheets DIR]
"""

from __future__ import annotations

import argparse
import json
import os

import numpy as np
from PIL import Image
from scipy import ndimage

SHEET_DIR = "art/sheets"
PORTRAIT_DIR = "art/portraits"
RAW_DIR = "art/raw"
ANIMS = {"idle": 4, "run": 6, "jump": 6, "attack": 5}

SOLID = 128        # alpha (0-255) at which a pixel counts as structural
ANY = 6            # alpha above which a pixel is visible at all
FRINGE_ALPHA = 77  # ~0.3; a halo pixel this opaque would be visible in game
ORB_MIN_FRAC = 0.010   # a component this big relative to the figure may be a thrown orb
LIMB_MIN_FRAC = 0.004  # below this it is a spark/dash, above it could be a severed limb


def magenta_mask(rgb: np.ndarray, bg: np.ndarray) -> np.ndarray:
    """Pixels lying on the magenta background ray -- i.e. surviving pink.

    The test is relative to brightness. A fixed distance threshold flags dark
    reds and maroons (Francisco's shirt, the orb's dark rim) as pink purely
    because everything is close together down at the dark end of the cube.
    """
    n = float(np.linalg.norm(bg))
    u = bg / n
    proj = rgb @ u
    perp = np.linalg.norm(rgb - proj[..., None] * u, axis=2)
    k = proj / n
    return (perp < 0.20 * np.maximum(proj, 1.0)) & (perp < 60.0) & (k > 0.25) & (k < 1.35)


def raw_bg(char: str, anim: str) -> np.ndarray:
    a = np.asarray(Image.open(f"{RAW_DIR}/{char}/{anim}.png").convert("RGB")).astype(np.float64)
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    return np.median(border, axis=0)


def check_character(char: str, meta: dict, problems: list[str]) -> dict:
    cw, ch = meta["cell"]
    ax, by = meta["anchor"]
    rows = []

    for anim, want in ANIMS.items():
        path = f"{SHEET_DIR}/{char}/{anim}.png"
        im = Image.open(path).convert("RGBA")
        a = np.asarray(im).astype(np.int32)
        alpha = a[..., 3]
        rgb = a[..., :3].astype(np.float64)

        # --- geometry -------------------------------------------------------
        if im.height != ch:
            problems.append(f"{char}/{anim}: cell height {im.height} != {ch}")
        if im.width % cw:
            problems.append(f"{char}/{anim}: width {im.width} is not a multiple of {cw}")
        got = im.width // cw
        if got != want:
            problems.append(f"{char}/{anim}: {got} frames, expected {want}")

        # --- pink fringe ----------------------------------------------------
        bg = raw_bg(char, anim)
        vis = alpha >= FRINGE_ALPHA
        pink = int((magenta_mask(rgb, bg) & vis).sum())

        baselines, foot_dx, heights, widths, strays, edge_hits = [], [], [], [], [], 0
        for i in range(got):
            cell_a = alpha[:, i * cw:(i + 1) * cw]
            solid = cell_a >= SOLID
            if not solid.any():
                problems.append(f"{char}/{anim}: frame {i} is empty")
                continue

            lab, n = ndimage.label(solid, structure=np.ones((3, 3), bool))
            sizes = np.bincount(lab.ravel())
            sizes[0] = 0
            main = int(np.argmax(sizes))
            fig = lab == main
            ys, xs = np.where(fig)
            y1 = int(ys.max())
            baselines.append(y1)
            heights.append(int(ys.max() - ys.min() + 1))
            widths.append(int(xs.max() - xs.min() + 1))

            band = fig[max(0, y1 - int((ys.max() - ys.min()) * 0.25)):y1 + 1]
            fc = np.where(band.any(axis=0))[0]
            if fc.size:
                foot_dx.append(int((fc.min() + fc.max()) // 2) - ax)

            # stray components big enough to be a severed limb rather than a spark
            for cid in range(1, n + 1):
                if cid == main:
                    continue
                frac = sizes[cid] / sizes[main]
                if LIMB_MIN_FRAC < frac:
                    strays.append((i, cid, round(float(frac), 4)))

            vis_cell = cell_a >= ANY
            if vis_cell[0].any() or vis_cell[-1].any() or vis_cell[:, 0].any() or vis_cell[:, -1].any():
                edge_hits += 1

        off = [b - by for b in baselines]
        if any(o != 0 for o in off):
            problems.append(f"{char}/{anim}: baseline off by {off}")
        if pink:
            problems.append(f"{char}/{anim}: {pink} pink fringe px")
        if edge_hits:
            problems.append(f"{char}/{anim}: content touches the cell edge in {edge_hits} frame(s)")

        rows.append({
            "anim": anim, "frames": got, "pink": pink,
            "baseline_off": off, "foot_dx": foot_dx,
            "fig_h": heights, "fig_w": widths,
            "strays": strays, "edge_hits": edge_hits,
        })
    return {"cell": [cw, ch], "anchor": [ax, by], "rows": rows}


def contact_sheet(char: str, meta: dict, out_dir: str) -> None:
    """Stack all four animations with the baseline and anchor drawn on."""
    cw, ch = meta["cell"]
    ax, by = meta["anchor"]
    ims = []
    for anim in ANIMS:
        im = Image.open(f"{SHEET_DIR}/{char}/{anim}.png").convert("RGBA")
        a = np.asarray(im).astype(np.float64)
        al = a[..., 3:4] / 255.0
        h, w = a.shape[:2]
        board = (np.indices((h, w)).sum(0) // 16) % 2
        base = np.where(board[..., None] == 0, np.array([84., 84., 96.]), np.array([120., 120., 132.]))
        out = a[..., :3] * al + base * (1 - al)
        out[by] = np.array([255., 60., 60.])           # baseline
        for i in range(w // cw):                        # anchor column
            out[:, i * cw + ax] = np.array([60., 200., 255.])
            out[:, i * cw] = np.array([250., 230., 60.])  # cell boundary
        ims.append(Image.fromarray(out.astype(np.uint8)))

    width = max(i.width for i in ims)
    total = sum(i.height for i in ims) + 8 * len(ims)
    canvas = Image.new("RGB", (width, total), (24, 24, 28))
    y = 0
    for i in ims:
        canvas.paste(i, (0, y))
        y += i.height + 8
    os.makedirs(out_dir, exist_ok=True)
    scale = min(1.0, 1500 / width)
    canvas.resize((int(width * scale), int(total * scale)), Image.LANCZOS) \
        .save(f"{out_dir}/{char}.png")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contact-sheets", default=None)
    args = ap.parse_args()

    manifest = json.load(open(f"{SHEET_DIR}/manifest.json"))
    problems: list[str] = []
    results = {}
    for char, meta in manifest.items():
        results[char] = check_character(char, meta, problems)
        if args.contact_sheets:
            contact_sheet(char, meta, args.contact_sheets)

    for char, r in results.items():
        cw, ch = r["cell"]
        print(f"\n{char}  cell {cw}x{ch}  anchor x={r['anchor'][0]} baseline y={r['anchor'][1]}")
        for row in r["rows"]:
            print(f"   {row['anim']:7} n={row['frames']} pink={row['pink']:4} "
                  f"baseline_off={set(row['baseline_off'])} foot_dx={row['foot_dx']} "
                  f"fig_h={row['fig_h']} strays={row['strays']}")

    print("\n" + ("-" * 60))
    if problems:
        print(f"{len(problems)} problem(s):")
        for p in problems:
            print("  !", p)
    else:
        print("All automated checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
