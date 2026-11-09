#!/usr/bin/env python3
"""
Generated art (Higgsfield) -> game-ready pixel art.

Sources live in art/gen/src/ (what the generators returned, kept so this is
reproducible). This script converts them onto the game's 640x360 pixel grid
with the same rules the kids use -- area-downsample, hard edges, a fixed
palette per sprite, the 1px dark outline -- so generated and procedural art
sit together without one looking "higher resolution" than the other.

Writes into art/world/pride/ and art/pixel/, overriding the procedural
placeholders from make_world_art.py where a generated source exists.

Parts:
    bg       far.png, mid.png             (bg_far.png, bg_mid.png)
    kids     art/gen/attack/<Kid>.png     (slash/<kid>.png: 2x2 Keyblade slash)
             -> then run tools/pixelize.py to put the slash in the kids' sheets
    sprites  shadow.png, hyena.png, simba.png + sprites.json  (*_sheet.png)
    tiles    tiles.png, grass_fringe.png + world.json 'tileset'
             (earth_tex, rock_tex, ground_lip or grass_strip)
    scenery  platform.png, mover.png, acacia_N.png, savepoint.png, keyhole.png
             (platform, acacias, savepoint_src, keyhole_src)

Order matters: tools/make_world_art.py rewrites far/mid/tiles/world.json with
the procedural versions, so run it first and this script after it.

Worlds: each world has its own sources (art/gen/src for the Pride Lands,
art/gen/<world> for the others) and output folder art/world/<world>; see
WORLDS below. The kids' slash is shared and built with the Pride Lands.

Usage:
    python tools/build_gen_art.py                       # every part, Pride Lands
    python tools/build_gen_art.py kids tiles            # only some parts
    python tools/build_gen_art.py --world arendelle     # every part, Arendelle
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pixelize import downsample, make_palette, finish          # noqa: E402
from process_art import estimate_background, key_image          # noqa: E402

SRC = 'art/gen/src'
WORLD = 'art/world/pride'
H = 360
OUTLINE = (26, 18, 30)
ST8 = np.ones((3, 3), bool)
BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0


def quantize(rgb, mask, ncol):
    pal = make_palette([(rgb, mask)], ncol)
    q = np.asarray(Image.fromarray(rgb, 'RGB').quantize(palette=pal, dither=Image.Dither.NONE).convert('RGB'))
    out = np.zeros((*mask.shape, 4), np.uint8)
    out[mask, :3] = q[mask]; out[mask, 3] = 255
    return out


def key_white(im):
    """Generated sprites come on flat white. Key it like the magenta pipeline,
    but against white: anything close to the border colour and bright is out."""
    a = np.asarray(im.convert('RGB')).astype(np.float64)
    bg = estimate_background(a)
    return key_image(a, bg)


# --- backgrounds ---------------------------------------------------------------

def build_far():
    im = Image.open(f'{SRC}/bg_far.png').convert('RGBA')
    f = H / im.height
    rgb, mask = downsample(im, f)
    out = quantize(rgb, mask, 48)
    Image.fromarray(out, 'RGBA').save(f'{WORLD}/far.png')
    print('far', out.shape[1], 'x', out.shape[0])


def build_mid():
    im = Image.open(f'{SRC}/bg_mid.png').convert('RGB')
    a = np.asarray(im).astype(np.float64)
    rgb, alpha, _ = key_image(a, estimate_background(a))
    # The generator painted faint "ghost" trees floating in the magenta sky.
    # Real trees are joined to the hills by their trunks; keep only shapes that
    # are connected to the bottom of the image.
    solid = alpha >= 0.5
    lab, n = ndimage.label(solid, structure=ST8)
    grounded = set(np.unique(lab[-3:, :])) - {0}
    keep = np.isin(lab, list(grounded))
    keep = ndimage.binary_dilation(keep, ST8, iterations=2) & (alpha > 0)
    alpha = np.where(keep, alpha, 0.0)
    rgba = np.concatenate([rgb, alpha[..., None] * 255], -1).astype(np.uint8)
    f = H / im.height
    rgb2, mask = downsample(Image.fromarray(rgba, 'RGBA'), f)
    out = quantize(rgb2, mask, 40)
    # Mirror-double so the layer tiles seamlessly in a TileSprite.
    out = np.concatenate([out, out[:, ::-1]], 1)
    Image.fromarray(out, 'RGBA').save(f'{WORLD}/mid.png')
    print('mid', out.shape[1], 'x', out.shape[0])


# --- kids: Keyblade slash ------------------------------------------------------
#
# Each kid's slash comes back from the generator as a 2x2 grid on magenta:
#   ready | wind-up
#   strike | follow-through
# The figures are not inside tidy quadrants (a raised Keyblade crosses the
# middle line), so frames are found as connected shapes instead of by cutting.

SLASH_SRC = 'art/gen/src/slash'
ATTACK_OUT = 'art/gen/attack'
SLASH_CHARS = ['Baltazar', 'Francisco', 'Jo', 'Olimpia', 'Pedro', 'Sara']


def find_figures(alpha, n, by_x=False, min_ratio=0.2):
    """The n biggest shapes, with stray bits (a dangling keychain, a blade tip
    the generator drew detached) given to the nearest of them."""
    solid = alpha >= 0.5
    lab, cnt = ndimage.label(solid, structure=ST8)
    sizes = np.bincount(lab.ravel()); sizes[0] = 0
    order = list(np.argsort(sizes)[::-1][:n])
    if len(order) < n or sizes[order[-1]] < min_ratio * sizes[order[0]]:
        raise SystemExit(f'expected {n} figures, found sizes {sorted(sizes)[-6:]}')
    boxes = ndimage.find_objects(lab)
    owner = np.zeros_like(lab)
    for i, k in enumerate(order):
        owner[lab == k] = i + 1
    for k in range(1, cnt + 1):
        if k in order or sizes[k] < 40:
            continue
        sy, sx = boxes[k - 1]
        cy, cx = (sy.start + sy.stop) / 2, (sx.start + sx.stop) / 2
        best, bd = None, 1e9
        for i, j in enumerate(order):
            by, bx = boxes[j - 1]
            dy = max(by.start - cy, 0, cy - by.stop)
            dx = max(bx.start - cx, 0, cx - bx.stop)
            if dx + dy < bd:
                best, bd = i, dx + dy
        if bd < 60:
            owner[lab == k] = best + 1
    # Reading order: top row, then bottom row; left to right within a row.
    cents = []
    for i in range(n):
        ys, xs = np.where(owner == i + 1)
        cents.append((ys.mean(), xs.mean(), i))
    mid = alpha.shape[0] / 2
    cents.sort(key=(lambda c: c[1]) if by_x else (lambda c: (c[0] > mid, c[1])))
    return owner, [c[2] + 1 for c in cents]


def feet(mask):
    """(left edge of the back foot, bottom row) of a figure facing right. The
    Keyblade is always in front, so the back edge of the feet is a stable
    reference even when the blade sweeps down past the knees."""
    ys, xs = np.where(mask)
    y0, y1 = ys.min(), ys.max()
    band = mask[y1 - int((y1 - y0) * 0.12):y1 + 1]
    cols = np.where(band.any(0))[0]
    left = int(cols.min())
    # Bottom row measured on the back half only (blade tips can dip lower).
    back = mask[:, left:left + max(4, (xs.max() - left) // 3)]
    return left, int(np.where(back.any(1))[0].max()), cols


def build_slash(char):
    p = f'{SLASH_SRC}/{char.lower()}.png'
    if not os.path.exists(p):
        print('  no slash for', char)
        return
    a = np.asarray(Image.open(p).convert('RGB')).astype(np.float64)
    rgb, alpha, _ = key_image(a, estimate_background(a))
    owner, ids = find_figures(alpha, 4)
    figs = []
    for k in ids:
        m = ndimage.binary_dilation(owner == k, ST8, iterations=2) & (alpha > 0)
        left, bottom, cols = feet(owner == k)
        figs.append(dict(mask=m, left=left, bottom=bottom, cols=cols))
    # Feet centre measured on the ready pose (blade held high, nothing near the
    # feet), then carried to the other frames as an offset from the back foot.
    d = (figs[0]['cols'].min() + figs[0]['cols'].max()) / 2 - figs[0]['left']
    L = R = T = B = 0
    for f in figs:
        ys, xs = np.where(f['mask'])
        f['ax'] = int(round(f['left'] + d)); f['ay'] = f['bottom']
        f['box'] = (xs.min(), ys.min(), xs.max(), ys.max())
        L = max(L, f['ax'] - xs.min()); R = max(R, xs.max() - f['ax'])
        T = max(T, f['ay'] - ys.min()); B = max(B, ys.max() - f['ay'])
    fw, fh = L + R + 1, T + B + 1
    rgba = np.concatenate([rgb, alpha[..., None] * 255], -1).astype(np.uint8)
    strip = np.zeros((fh, fw * len(figs), 4), np.uint8)
    for i, f in enumerate(figs):
        x0, y0, x1, y1 = f['box']
        crop = rgba[y0:y1 + 1, x0:x1 + 1].copy()
        crop[~f['mask'][y0:y1 + 1, x0:x1 + 1]] = 0
        ox, oy = i * fw + L - (f['ax'] - x0), T - (f['ay'] - y0)
        region = strip[oy:oy + crop.shape[0], ox:ox + crop.shape[1]]
        sel = crop[..., 3] > 0
        region[sel] = crop[sel]
    os.makedirs(ATTACK_OUT, exist_ok=True)
    Image.fromarray(strip, 'RGBA').save(f'{ATTACK_OUT}/{char}.png')
    json.dump({'frame': [int(fw), int(fh)], 'anchor': [int(L), int(T)],
               'frames': ['ready', 'windup', 'strike', 'follow'],
               'source': p}, open(f'{ATTACK_OUT}/{char}.json', 'w'), indent=2)
    print(f'  {char}: 4 frames {fw}x{fh}, feet at {L},{T}')


def build_kids():
    for c in SLASH_CHARS:
        build_slash(c)


# --- enemies and the friend ----------------------------------------------------
#
# 3x2 grids of six frames on magenta, side view facing right. Frames 0-3 are the
# walk/run cycle; 4 and 5 are poses (see SPRITES). Everything is scaled by one
# factor per sheet (from the walk frames' median height), so poses keep their
# true size relative to the walk, and each frame stands bottom-centre in a
# shared cell -- the game's sprites use origin (0.5, 1).

SPRITES_PRIDE = {
    'shadow': dict(src='shadow_sheet.png', height=34, colors=14, body=[16, 26], lift={5: 8}, inky=True,
                   anims={'walk': [0, 3], 'lunge': [5, 5]}, poses={'crouch': 4},
                   fps={'walk': 8, 'lunge': 1}, puddle=True),
    'hyena': dict(src='hyena_sheet.png', height=36, colors=22, body=[40, 26],
                  anims={'walk': [0, 3]}, poses={'crouch': 4, 'rest': 5}, fps={'walk': 10}),
    'simba': dict(src='simba_sheet.png', height=30, colors=22, body=[30, 22], lift={5: 6},
                  anims={'walk': [0, 3]}, poses={'crouch': 4, 'pounce': 5}, fps={'walk': 10}),
}
SPRITES_ARENDELLE = {
    'wolf': dict(src='wolf_sheet.png', height=38, colors=20, body=[40, 26],
                 anims={'walk': [0, 3]}, poses={'crouch': 4, 'rest': 5}, fps={'walk': 10}),
    'olaf': dict(src='olaf_sheet.png', height=38, colors=18, body=[20, 30], lift={5: 6},
                 anims={'walk': [0, 3]}, poses={'throw': 4, 'air': 5}, fps={'walk': 9}),
}
SPRITES_SEOUL = {
    'demon': dict(src='demon_sheet.png', height=38, colors=20, body=[22, 30],
                  anims={'walk': [0, 3]}, poses={'crouch': 4, 'rest': 5}, fps={'walk': 10}),
    'derpy': dict(src='derpy_sheet.png', height=32, colors=22, body=[30, 22], lift={5: 6},
                  anims={'walk': [0, 3]}, poses={'crouch': 4, 'pounce': 5}, fps={'walk': 10}),
}
SPRITES_SPIDER = {
    'goblin': dict(src='goblin_sheet.png', height=36, colors=20, body=[24, 28],
                   anims={'walk': [0, 3]}, poses={'crouch': 4, 'rest': 5}, fps={'walk': 10}),
}

# Per-world sources and settings. Each world reads art/gen/<src> and writes
# art/world/<id>. Terrain: (level letter, texture, colours, tone, top edge),
# top edge 'lip' = the generated ground edge + fringe, 'rim' = a lit rim.
WORLDS = {
    'pride': dict(src='art/gen/src', out='art/world/pride', sprites=SPRITES_PRIDE,
                  terrain=[('G', 'earth_tex.png', 14, None, 'lip'),
                           ('R', 'rock_tex.png', 14, [0.96, 0.84, 0.74], 'rim')],
                  slippery=[], trees=('acacias.png', [118, 138, 112], 22), shared_from=None,
                  # the hippo bounce pad is bigger than a snow pad; crumbling
                  # sandstone is the platform art, cracked (see cracked_platform)
                  bounce_w=58, crumble_src='platform.png',
                  # the hippo's pink belly and cheeks are too close to magenta
                  # for the colour key: cut it out by its outline instead
                  bounce_key='flood'),
    'arendelle': dict(src='art/gen/arendelle', out='art/world/arendelle', sprites=SPRITES_ARENDELLE,
                      terrain=[('G', 'earth_tex.png', 14, None, 'lip'),
                               ('R', 'ice_tex.png', 14, {'mul': [0.86, 0.92, 0.98], 'sat': 0.62}, 'rim'),
                               ('I', 'lake_tex.png', 12, None, 'rim')],
                      slippery=['I'], trees=('pines.png', [134, 156, 120], 20), shared_from='pride'),
    # World 3, the K-pop demon hunters' city: tiled hanok roofs over brick,
    # glass towers, neon platforms, speaker bounce pads and beat platforms.
    'seoul': dict(src='art/gen/seoul', out='art/world/seoul', sprites=SPRITES_SEOUL,
                  terrain=[('G', 'earth_tex.png', 14, {'mul': [1.3, 1.22, 1.3], 'sat': 1.0}, 'lip'),
                           ('R', 'rock_tex.png', 16, None, 'rim')],
                  slippery=[], trees=('decor.png', [126, 84, 136], 22), shared_from='pride',
                  bounce_w=50, bounce_key='flood', crumble_src='platform.png', beat=True),
    # World 4, the spider hero's city: sunny rooftops of brick under stone
    # parapets, stone towers, steel girders and a web trampoline.
    'spider': dict(src='art/gen/spider', out='art/world/spider', sprites=SPRITES_SPIDER,
                   terrain=[('G', 'earth_tex.png', 14, None, 'lip'),
                            ('R', 'rock_tex.png', 16, None, 'rim')],
                   slippery=[], trees=('decor.png', [118, 150, 92], 22), shared_from='pride',
                   bounce_w=52, crumble_src='platform.png', platform='girder', bounce_unpink=True,
                   trees_min_ratio=0.08),                 # the antenna mast is thin
}
CFG = WORLDS['pride']


def puddle_frame(w, h):
    """The melted Shadow: a flat pool of darkness with two eyes peeking out."""
    out = np.zeros((h, w, 4), np.uint8)
    cx, rw, rh = w / 2 - 0.5, min(w / 2 - 1, 13), 3.2
    yy, xx = np.mgrid[0:h, 0:w]
    cy = h - 1 - rh
    d = ((xx - cx) / rw) ** 2 + ((yy - cy) / rh) ** 2
    out[d <= 1.0] = (*OUTLINE, 255)
    out[d <= 0.55] = (44, 30, 58, 255)
    for ex in (-3, 2):
        out[int(cy) - 1, int(cx) + ex:int(cx) + ex + 2] = (255, 226, 92, 255)
    return out


def inky(rgb):
    """Heartless black: every dark pixel onto one cold indigo ramp (keying
    leaves a warm magenta cast on dark edges), the glowing eyes untouched."""
    a = rgb.astype(np.float64)
    lum = a @ np.array([0.299, 0.587, 0.114])
    eye = (a[..., 0] > 150) & (a[..., 1] > 120) & (a[..., 2] < a[..., 1] * 0.8)
    ramp = np.stack([lum * 0.78 + 6, lum * 0.66 + 4, lum * 1.05 + 14], -1)
    out = np.where(eye[..., None], a, ramp)
    return np.clip(out, 0, 255).astype(np.uint8)


def build_sprite(name, cfg):
    p = f'{SRC}/{cfg["src"]}'
    if not os.path.exists(p):
        print('  no source for', name)
        return None
    a = np.asarray(Image.open(p).convert('RGB')).astype(np.float64)
    rgb, alpha, _ = key_image(a, estimate_background(a))
    owner, ids = find_figures(alpha, 6)
    # Reading order for a 3x2 grid is what find_figures already returns.
    rgba = np.concatenate([rgb, alpha[..., None] * 255], -1).astype(np.uint8)
    crops = []
    for k in ids:
        m = ndimage.binary_dilation(owner == k, ST8, iterations=2) & (alpha > 0)
        ys, xs = np.where(m)
        y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
        c = rgba[y0:y1 + 1, x0:x1 + 1].copy()
        c[~m[y0:y1 + 1, x0:x1 + 1]] = 0
        crops.append(Image.fromarray(c, 'RGBA'))
    walk_h = float(np.median([c.height for c in crops[:4]]))
    f = (cfg['height'] - 2) / walk_h
    raw = [downsample(c, f) for c in crops]
    if cfg.get('inky'):
        raw = [(inky(r), m) for r, m in raw]
    pal = make_palette(raw, cfg['colors'])
    done = [finish(r, m, pal, OUTLINE) for r, m in raw]
    # Trim each frame to its pixels, then sit it bottom-centre in one cell.
    trimmed = []
    for px in done:
        ys, xs = np.where(px[..., 3] > 0)
        trimmed.append(px[ys.min():ys.max() + 1, xs.min():xs.max() + 1])
    lift = cfg.get('lift', {})
    cw = max(t.shape[1] for t in trimmed) + 2
    ch = max(t.shape[0] + lift.get(i, 0) for i, t in enumerate(trimmed)) + 1
    cw += cw % 2                                    # even, so 'centre' is exact
    frames = []
    for i, t in enumerate(trimmed):
        cell = np.zeros((ch, cw, 4), np.uint8)
        h, w = t.shape[:2]
        ox, oy = (cw - w) // 2, ch - h - lift.get(i, 0)
        cell[oy:oy + h, ox:ox + w] = t
        frames.append(cell)
    meta = {'frame': [cw, ch], 'body': cfg['body'], 'anims': cfg['anims'],
            'fps': cfg.get('fps', {}), 'source': 'generated'}
    meta.update(cfg.get('poses', {}))
    if cfg.get('puddle'):
        frames.append(puddle_frame(cw, ch))
        meta['puddle'] = len(frames) - 1
    Image.fromarray(np.concatenate(frames, 1), 'RGBA').save(f'{WORLD}/{name}.png')
    print(f'  {name}: {len(frames)} frames {cw}x{ch}')
    return meta


def build_sprites():
    path = f'{WORLD}/sprites.json'
    sprites = json.load(open(path)) if os.path.exists(path) else {}
    for name, cfg in CFG['sprites'].items():
        meta = build_sprite(name, cfg)
        if meta:
            sprites[name] = meta
    json.dump(sprites, open(path, 'w'), indent=2)


# --- ground tiles ----------------------------------------------------------------
#
# Earth and rock are generated seamless textures, 128px square on screen. A
# terrain tile shows the 16x16 piece of the texture under its world position
# (8x8 variants), so the ground reads as one continuous painted surface rather
# than a stamp repeated every 16px. Each tile kind (top/side/corner) is the
# texture plus an edge treatment: golden grass on dirt tops, a sunlit rim on
# rock tops, a shaded lip on walls.
#
# Index = terrain base + kind * V*V + (y % V) * V + (x % V); see js/level.js.

TILE = 16
V = 8                                   # variants per axis -> 128px texture period
KINDS = 8                               # top single/left/mid/right, wall L/R, inside x2
TILES_COLS = 16


def seamless(img):
    """Make a texture wrap: blend it with a half-shifted copy of itself, the
    copy taking over near the edges (where its content is the continuous
    middle of the original)."""
    h, w = img.shape[:2]
    sh = np.roll(np.roll(img, h // 2, 0), w // 2, 1)
    yy, xx = np.mgrid[0:h, 0:w]
    wy = np.minimum(yy + 0.5, h - yy - 0.5) / (h / 2)
    wx = np.minimum(xx + 0.5, w - xx - 0.5) / (w / 2)
    wgt = np.clip(np.minimum(wx, wy) * 2.5, 0, 1)[..., None]
    return img * wgt + sh * (1 - wgt)


def texture(name, ncol):
    im = Image.open(f'{SRC}/{name}').convert('RGB')
    s = min(im.size)
    im = im.crop((0, 0, s, s)).resize((TILE * V, TILE * V), Image.BOX)
    a = seamless(np.asarray(im).astype(np.float64))
    rgb = np.clip(a, 0, 255).astype(np.uint8)
    q = quantize(rgb, np.ones(rgb.shape[:2], bool), ncol)
    return q[..., :3].astype(np.float64)


def grass_strip():
    """Golden grass band, keyed, TILE*V wide and wrapping, with its alpha."""
    im = Image.open(f'{SRC}/grass_strip.png').convert('RGB')
    a = np.asarray(im).astype(np.float64)
    rgb, alpha, _ = key_image(a, estimate_background(a))
    # The real band is the longest run of nearly-solid rows (the generator
    # also painted a faint ghost of it higher up); its tufts are the rows
    # just above, up to where coverage dies out.
    cov = (alpha > 0.5).mean(1)
    best, run, start = (0, 0), 0, 0
    for y, c in enumerate(cov > 0.6):
        if c:
            if not run: start = y
            run += 1
            if run > best[1] - best[0]: best = (start, y + 1)
        else:
            run = 0
    y0, y1 = best[0], best[1] - 1
    while y0 > 0 and cov[y0 - 1] > 0.03:
        y0 -= 1
    band = np.concatenate([rgb, alpha[..., None] * 255], -1)[y0:y1 + 1].astype(np.uint8)
    # Keep the band's real proportions: scale so it spans the texture width
    # twice (so a tuft is a few pixels wide), then wrap it.
    h = band.shape[0]
    f = (TILE * V * 2) / band.shape[1]
    rgb2, mask = downsample(Image.fromarray(band, 'RGBA'), f)
    rgb2, mask = rgb2[:, :TILE * V], mask[:, :TILE * V]
    q = quantize(rgb2, mask, 10)
    # Only the top 9 rows are used: tufts + the dense part of the band.
    solid_rows = np.where(mask.mean(1) > 0.9)[0]
    top = max(0, (solid_rows.min() if len(solid_rows) else 0) - 4)
    q = q[top:top + 9]
    return q


FRINGE = 8               # grass tips drawn above the ground surface, behind the kid


def lip_strip():
    """The generated top edge of the ground -- tall golden grass, the dark
    shadow it casts, the first band of soil -- (TILE + FRINGE) rows tall and
    wrapping every TILE*V pixels. The top FRINGE rows are the grass tips, which
    the game draws above the surface (art/world/pride/grass_fringe.png); the
    rest is painted into the top ground tiles. Returns (tile_part, fringe), or
    the thin grass strip and None when there's no lip source."""
    p = f'{SRC}/ground_lip.png'
    if not os.path.exists(p):
        return grass_strip(), None
    a = np.asarray(Image.open(p).convert('RGB')).astype(np.float64)
    bg = np.median(a[:8].reshape(-1, 3), 0)          # only the top is magenta
    rgb, alpha, _ = key_image(a, bg)
    solid = alpha > 0.5
    cov = solid.mean(1)
    y_top = int(np.where(cov > 0.02)[0].min())
    lum = rgb @ np.array([0.299, 0.587, 0.114])
    rowl = np.array([lum[y][solid[y]].mean() if solid[y].any() else 255 for y in range(a.shape[0])])
    lo, hi = y_top + 20, y_top + int(0.75 * (a.shape[0] - y_top))
    y_dark = lo + int(np.argmin(rowl[lo:hi]))          # the shadow under the grass
    y_end = y_dark + int((y_dark - y_top) * 0.2)
    band = np.concatenate([rgb, alpha[..., None] * 255], -1)[y_top:y_end + 1]
    band = np.clip(band, 0, 255).astype(np.uint8)
    rows = TILE + FRINGE
    rgb2, mask = downsample(Image.fromarray(band, 'RGBA'), rows / band.shape[0])
    rgb2, mask = rgb2[:rows], mask[:rows]
    # Averaging thin blades turns them to olive mush: sharpen and brighten.
    f = rgb2.astype(np.float64)
    blur = ndimage.uniform_filter(f, size=(3, 3, 1))
    f = np.clip((f + (f - blur) * 1.1) * 1.1, 0, 255)
    rgb2 = f.astype(np.uint8)
    # Half the period, then mirrored: a mirrored pair wraps with no seam.
    half = TILE * V // 2
    rgb2, mask = rgb2[:, :half], mask[:, :half]
    rgb2 = np.concatenate([rgb2, rgb2[:, ::-1]], 1)
    mask = np.concatenate([mask, mask[:, ::-1]], 1)
    q = quantize(rgb2, mask, 14)
    return q[FRINGE:], q[:FRINGE]


def edge_tiles(tex, top_fn, wall_shade):
    """All KINDS x V x V tiles for one terrain."""
    out = []
    P = TILE * V
    for kind in range(KINDS):
        top = kind <= 3
        left = kind in (0, 1, 4)
        right = kind in (0, 3, 5)
        for vy in range(V):
            for vx in range(V):
                t = np.zeros((TILE, TILE, 4), np.uint8)
                piece = tex[vy * TILE:(vy + 1) * TILE, vx * TILE:(vx + 1) * TILE].copy()
                if left:
                    piece[:, 0] = OUTLINE; piece[:, 1:3] *= wall_shade
                if right:
                    piece[:, -1] = OUTLINE; piece[:, -3:-1] *= wall_shade
                t[..., :3] = np.clip(piece, 0, 255).astype(np.uint8); t[..., 3] = 255
                if top:
                    top_fn(t, vx)
                if top and left:
                    t[0, 0:2, 3] = 0; t[1, 0, 3] = 0
                if top and right:
                    t[0, -2:, 3] = 0; t[1, -1, 3] = 0
                out.append(t)
    return out


def build_tiles():
    terr = CFG['terrain']
    need = [t[1] for t in terr]
    missing = [n for n in need if not os.path.exists(f'{SRC}/{n}')]
    if missing:
        print('  tiles: missing sources', missing)
        return
    texes = {}
    for letter, name, ncol, tone, _ in terr:
        tx = texture(name, ncol)
        if isinstance(tone, dict):
            # {'mul': per-channel factor, 'sat': saturation kept (0..1)}
            lum = (tx @ np.array([0.299, 0.587, 0.114]))[..., None]
            tx = lum + (tx - lum) * tone.get('sat', 1.0)
            tx = tx * tone.get('mul', [1, 1, 1])
        elif tone:
            tx = tx * tone
        texes[letter] = np.clip(tx, 0, 255)
    grass, fringe = lip_strip()
    gh = grass.shape[0]
    if fringe is not None:
        Image.fromarray(fringe, 'RGBA').save(f'{WORLD}/grass_fringe.png')
    yy, xx = np.mgrid[0:TILE, 0:TILE]

    def grass_top(t, vx):
        g = grass[:, vx * TILE:(vx + 1) * TILE]
        sel = g[..., 3] > 0
        # Above the dense line, a pixel with no grass is open sky.
        dense = np.where((g[..., 3] > 0).mean(1) > 0.9)[0]
        cut = dense.min() if len(dense) else 3
        sky = ~sel.copy(); sky[cut:] = False
        if gh >= TILE:
            # The lip's own soil fades into the earth texture over its last
            # rows (ordered dither), so the two never meet at a hard line.
            fade = (yy >= TILE - 5) & (BAYER[yy % 4, xx % 4] < (yy - (TILE - 6)) / 6.0)
            sel = sel & ~fade
        t[:gh][sel] = g[sel]
        t[:gh][sky] = 0
        # a dark root line where a thin grass strip meets the earth
        if gh < TILE:
            t[gh, :, :3] = (t[gh, :, :3] * 0.72).astype(np.uint8)

    def rock_top(t, vx):
        hi = np.clip(t[0:2, :, :3].astype(np.float64) * [1.25, 1.22, 1.15] + 12, 0, 255)
        t[0:2, :, :3] = hi.astype(np.uint8)
        t[2, :, :3] = (t[2, :, :3] * 0.8).astype(np.uint8)

    tiles, bases = [], {}
    per = KINDS * V * V
    for letter, _, _, _, top in terr:
        bases[letter] = len(tiles)
        tiles += edge_tiles(texes[letter], grass_top if top == 'lip' else rock_top, 0.72)
    # One-way ledge tiles (hidden in the game when platform art exists): a thin
    # slab shaded in the first rocky terrain's own colours.
    rocky = next((texes[t[0]] for t in terr if t[4] == 'rim'), texes[terr[0][0]])
    cols = rocky.reshape(-1, 3)
    lum = cols @ np.array([0.299, 0.587, 0.114])
    order = np.argsort(lum)
    pick = lambda q: cols[order[int(q * (len(order) - 1))]]
    shade = [pick(0.97), pick(0.85), pick(0.6), pick(0.55), pick(0.5), pick(0.3), pick(0.15)]
    rng = np.random.default_rng(3)
    for kind in range(4):
        left, right = kind in (0, 1), kind in (0, 3)
        t = np.zeros((TILE, TILE, 4), np.uint8)
        for y, col in enumerate(shade):
            t[y, :, :3] = col.astype(np.uint8)
        speck = rng.random((3, TILE)) < 0.12
        t[2:5][speck, :3] = shade[5].astype(np.uint8)
        t[0:7, :, 3] = 255
        t[7, 2:TILE - 2, :3] = OUTLINE; t[7, 2:TILE - 2, 3] = 255
        if left:
            t[0:7, 0, 3] = 0; t[0, 1, 3] = 0; t[6, 1, 3] = 0; t[1:6, 1, :3] = OUTLINE
        if right:
            t[0:7, -1, 3] = 0; t[0, -2, 3] = 0; t[6, -2, 3] = 0; t[1:6, -2, :3] = OUTLINE
        tiles.append(t)
    rows = (len(tiles) + TILES_COLS - 1) // TILES_COLS
    sheet = np.zeros((rows * TILE, TILES_COLS * TILE, 4), np.uint8)
    for i, t in enumerate(tiles):
        y, x = divmod(i, TILES_COLS)
        sheet[y * TILE:(y + 1) * TILE, x * TILE:(x + 1) * TILE] = t
    Image.fromarray(sheet, 'RGBA').save(f'{WORLD}/tiles.png')
    n = len(terr)
    layout = {'variants': V, 'kindStride': V * V, 'terrain': bases,
              'ledge': n * per, 'solidMax': n * per - 1, 'count': len(tiles),
              'fringe': FRINGE if fringe is not None else 0,
              # Index ranges you slide on (a frozen lake).
              'slippery': [[bases[l], bases[l] + per - 1] for l in CFG['slippery']]}
    path, world = world_meta()
    world['tileset'] = layout
    json.dump(world, open(path, 'w'), indent=2)
    print(f'  tiles: {len(tiles)} in a {TILES_COLS}x{rows} grid', layout)


# --- scenery: platforms, trees, save point, Keyhole -------------------------------

PLATFORM_H = 28          # floating platform height on screen, grass to roots
BOUNCE_W = 44
CHEST_H = 22
GEM_H = 18
SAVE_W = 56
KEYHOLE_H = 76


def load_keyed(name, top_bg=False):
    a = np.asarray(Image.open(f'{SRC}/{name}').convert('RGB')).astype(np.float64)
    bg = np.median(a[:8].reshape(-1, 3), 0) if top_bg else estimate_background(a)
    rgb, alpha, _ = key_image(a, bg)
    return rgb, alpha


def cut_figure(rgb, alpha, owner, k):
    m = ndimage.binary_dilation(owner == k, ST8, iterations=2) & (alpha > 0)
    ys, xs = np.where(m)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    rgba = np.concatenate([rgb, alpha[..., None] * 255], -1)[y0:y1 + 1, x0:x1 + 1]
    rgba = np.clip(rgba, 0, 255).astype(np.uint8)
    rgba[~m[y0:y1 + 1, x0:x1 + 1]] = 0
    return rgba


def pixel_sprite(rgba, f, ncol, outline=True):
    rgb, mask = downsample(Image.fromarray(rgba, 'RGBA'), f)
    pal = make_palette([(rgb, mask)], ncol)
    if outline:
        px = finish(rgb, mask, pal, OUTLINE)
    else:
        px = quantize(rgb, mask, ncol)
    ys, xs = np.where(px[..., 3] > 0)
    return px[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def world_meta():
    p = f'{WORLD}/world.json'
    return p, (json.load(open(p)) if os.path.exists(p) else {'tile': TILE})


def platform_pieces(src):
    """Cut a generated platform into same-height pieces: (left cap, 48px
    wrapping middle, right cap, surface row)."""
    rgb, alpha = load_keyed(src)
    owner, ids = find_figures(alpha, 1)
    fig = cut_figure(rgb, alpha, owner, ids[0])
    px = pixel_sprite(fig, (PLATFORM_H - 2) / fig.shape[0], 18)
    solid = px[..., 3] > 0
    h, w = solid.shape
    # Walking surface: the first row the slab fills nearly edge to edge (the
    # grass tufts above it are decoration the feet stand in front of).
    inner = solid[:, 4:w - 4]
    surface = int(np.where(inner.mean(1) > 0.85)[0].min())
    left, right = px[:, 0:TILE], px[:, w - TILE:w]
    c = w // 2
    mid = px[:, c - 12:c + 12]
    mid = np.concatenate([mid, mid[:, ::-1]], 1)            # 48px, wraps
    return left, mid, right, surface


def girder_pieces():
    """World 4's steel I-beam, drawn straight at pixel size (the generators
    kept drawing it tilted, then flagged it): (left cap, 48px wrapping
    middle, right cap, surface row), 26px tall with the dark outline."""
    C = {'hi': (255, 150, 90), 'top': (226, 86, 46), 'face': (200, 70, 38), 'web': (172, 56, 32),
         'shade': (130, 40, 24), 'deep': (96, 30, 20), 'hole': (52, 22, 20),
         'rivet': (255, 186, 120), 'rivs': (110, 34, 20)}
    H, W = 26, 48 + 32
    g = np.zeros((H, W, 4), np.uint8)
    g[..., 3] = 255
    def fill(y0, y1, x0, x1, c):
        g[y0:y1, x0:x1, :3] = C[c] if c in C else c
    fill(0, H, 0, W, OUTLINE)
    fill(1, H - 1, 0, W, 'web')
    fill(1, 2, 0, W, 'hi'); fill(2, 4, 0, W, 'top'); fill(4, 5, 0, W, 'shade'); fill(5, 6, 0, W, 'deep')
    fill(19, 20, 0, W, 'face'); fill(20, 23, 0, W, 'top'); fill(23, 25, 0, W, 'deep')
    yy, xx = np.mgrid[0:H, 0:W]
    for x0 in range(16, 16 + 48, 24):                    # two bays in the middle piece
        fill(6, 19, x0, x0 + 2, 'face'); fill(6, 19, x0 + 2, x0 + 3, 'shade')
        cx, cy, r = x0 + 13.5, 12, 3.6
        d2 = (xx - cx) ** 2 + (yy - cy) ** 2
        g[d2 <= r * r, :3] = C['hole']
        g[(d2 <= (r + 1) ** 2) & (d2 > r * r) & (yy > cy), :3] = C['face']
    for x in range(4, W - 4, 8):
        for y in (2, 21):
            g[y, x, :3] = C['rivet']; g[y, x + 1, :3] = C['rivs']
    # end caps: a darker end plate with the outline
    for x in (0,):
        fill(1, H - 1, 1, 3, 'shade')
    g[:, 0, :3] = OUTLINE
    left = g[:, 0:16].copy()
    mid = g[:, 16:64].copy()
    right = left[:, ::-1].copy()
    return left, mid, right, 1


def build_platform():
    """Floating platform pieces, all PLATFORM_H tall: single, left cap, three
    middles that wrap, right cap. The game draws a ledge run from these (the
    ledge tiles only provide the collision), and a moving platform is
    left + three middles + right."""
    if CFG.get('platform') == 'girder':
        left, mid, right, surface = girder_pieces()
    else:
        left, mid, right, surface = platform_pieces('platform.png')
    h = left.shape[0]
    single = np.concatenate([left[:, :TILE // 2], right[:, TILE // 2:]], 1)
    pieces = [single, left] + [mid[:, i * TILE:(i + 1) * TILE] for i in range(3)] + [right]
    Image.fromarray(np.concatenate(pieces, 1), 'RGBA').save(f'{WORLD}/platform.png')
    # Moving platforms are 5 tiles wide: a kid who holds 'right' through a
    # jump still has room to land.
    mover = np.concatenate([left, mid, right], 1)
    Image.fromarray(mover, 'RGBA').save(f'{WORLD}/mover.png')
    path, world = world_meta()
    world['platform'] = {'frame': [TILE, h], 'surface': surface, 'mids': 3,
                         'frames': {'single': 0, 'left': 1, 'mid': 2, 'right': 5}}
    world['mover'] = {'size': [mover.shape[1], h], 'surface': surface}
    json.dump(world, open(path, 'w'), indent=2)
    print(f'  platform: pieces {TILE}x{h}, surface row {surface}')


def build_crumble():
    """Crumbling platform: 4 tiles that crack and drop after you land."""
    if os.path.exists(f'{SRC}/crumble.png'):
        left, mid, right, surface = platform_pieces('crumble.png')
        img = np.concatenate([left, mid[:, :2 * TILE], right], 1)
    else:
        img, surface = cracked_platform()
    Image.fromarray(img, 'RGBA').save(f'{WORLD}/crumble.png')
    path, world = world_meta()
    world['crumble'] = {'size': [img.shape[1], img.shape[0]], 'surface': surface}
    json.dump(world, open(path, 'w'), indent=2)
    print('  crumble:', img.shape[1], 'x', img.shape[0])


def cracked_platform():
    """No generated crumble art: crack this world's own platform instead --
    left cap, two middles, right cap, darkened, with jagged dark cracks."""
    sheet = np.asarray(Image.open(f'{WORLD}/platform.png').convert('RGBA'))
    path, world = world_meta()
    fw = world['platform']['frame'][0]
    piece = lambda i: sheet[:, i * fw:(i + 1) * fw]
    img = np.concatenate([piece(1), piece(2), piece(3), piece(5)], 1).astype(np.int32)
    solid = img[..., 3] > 0
    img[solid, :3] = (img[solid, :3] * 0.86).astype(np.int32)
    rng = np.random.default_rng(11)
    h, w = solid.shape
    for x0 in range(6, w - 4, 11):                      # a crack every ~11px
        x, y = x0 + int(rng.integers(-2, 3)), 1
        while y < h - 2:
            if solid[y, x]:
                img[y, x, :3] = OUTLINE
            y += 1
            x = int(np.clip(x + rng.integers(-1, 2), 1, w - 2))
    surface = world['platform']['surface']
    return img.astype(np.uint8), surface


def build_beat():
    """Beat platforms (World 3): 4 tiles of this world's platform art, two
    frames -- the neon in hot pink for group 1, in cyan for group 2."""
    sheet = np.asarray(Image.open(f'{WORLD}/platform.png').convert('RGBA')).astype(np.float64)
    path, world = world_meta()
    fw = world['platform']['frame'][0]
    piece = lambda i: sheet[:, i * fw:(i + 1) * fw]
    img = np.concatenate([piece(1), piece(2), piece(3), piece(5)], 1)
    rgb, a = img[..., :3], img[..., 3]
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1)
    neon = (a > 0) & (mx > 120) & (sat > 0.35)
    lum = (rgb @ np.array([0.299, 0.587, 0.114])) / 255.0
    frames = []
    solid = a > 0
    # The walking surface: the first two solid rows of each column.
    top = np.zeros_like(solid)
    for x in range(solid.shape[1]):
        ys = np.where(solid[:, x])[0]
        if len(ys) > 2:
            top[ys[0] + 1:ys[0] + 3, x] = True
    for hue in ((255, 70, 170), (60, 230, 255)):
        f = img.copy()
        h = np.array(hue, np.float64)
        # The whole slab leans toward the group's colour, so it reads at a glance...
        f[solid, :3] = f[solid, :3] * 0.7 + h * 0.3
        t = np.clip(lum[neon] * 1.5, 0, 1)[:, None]
        f[neon, :3] = h * (0.55 + 0.45 * t) + 255 * np.clip(t - 0.75, 0, 1) * 1.6
        # ...with a glowing neon top edge you can stand on.
        f[top, :3] = h * 0.75 + 255 * 0.25
        frames.append(np.clip(f, 0, 255))
    out = np.concatenate(frames, 1).astype(np.uint8)
    Image.fromarray(out, 'RGBA').save(f'{WORLD}/beat.png')
    world['beat'] = {'frame': [img.shape[1], img.shape[0]], 'surface': world['platform']['surface']}
    json.dump(world, open(path, 'w'), indent=2)
    print('  beat:', img.shape[1], 'x', img.shape[0], 'x2')


STAGE_H = 150


def build_stage():
    """A backdrop behind the Keyhole (World 3's concert stage)."""
    rgb, alpha = load_keyed('stage_src.png')
    lab, n = ndimage.label(alpha >= 0.5, structure=ST8)
    sizes = np.bincount(lab.ravel()); sizes[0] = 0
    big = [k for k in range(1, n + 1) if sizes[k] > 400]          # drop specks
    owner = np.isin(lab, big).astype(int)
    fig = cut_figure(rgb, alpha, owner, 1)
    px = pixel_sprite(fig, (STAGE_H - 2) / fig.shape[0], 28)
    Image.fromarray(px, 'RGBA').save(f'{WORLD}/stage.png')
    path, world = world_meta()
    world['stage'] = {'size': [px.shape[1], px.shape[0]]}
    json.dump(world, open(path, 'w'), indent=2)
    print('  stage:', px.shape[1], 'x', px.shape[0])


def load_flood(name, tol=90):
    """Background = the magenta reachable from the image border; everything
    the dark outline encloses stays, whatever its colour (a pink belly too)."""
    a = np.asarray(Image.open(f'{SRC}/{name}').convert('RGB')).astype(np.float64)
    bg = estimate_background(a)
    near = np.linalg.norm(a - bg, axis=2) < tol
    lab, _ = ndimage.label(near, structure=ST8)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    alpha = (~np.isin(lab, list(edge))).astype(np.float64)
    return a, alpha


def build_bounce():
    """Bounce pad (a single sprite; the game squashes it)."""
    if CFG.get('bounce_key') == 'flood':
        rgb, alpha = load_flood('bounce_src.png')
    else:
        rgb, alpha = load_keyed('bounce_src.png')
    # Only the pad itself -- no floating sparkles or sleepy Zzz's around it.
    lab, n = ndimage.label(alpha >= 0.5, structure=ST8)
    sizes = np.bincount(lab.ravel()); sizes[0] = 0
    owner = (lab == int(np.argmax(sizes))).astype(int)
    owner = ndimage.binary_fill_holes(owner).astype(int)
    alpha = np.maximum(alpha, owner)
    fig = cut_figure(rgb, alpha, owner, 1)
    px = pixel_sprite(fig, (CFG.get('bounce_w', BOUNCE_W) - 2) / fig.shape[1], 16)
    if CFG.get('bounce_unpink'):
        # A white web over magenta comes out pink: give it back its white.
        f = px[..., :3].astype(np.float64)
        pink = (px[..., 3] > 0) & (np.minimum(f[..., 0], f[..., 2]) - f[..., 1] > 25)
        lum = f @ np.array([0.299, 0.587, 0.114])
        px[pink, :3] = np.clip(np.stack([lum[pink] * 1.25 + 20] * 3, -1), 0, 255).astype(np.uint8)
    Image.fromarray(px, 'RGBA').save(f'{WORLD}/bounce.png')
    path, world = world_meta()
    world['bounce'] = {'size': [px.shape[1], px.shape[0]]}
    json.dump(world, open(path, 'w'), indent=2)
    print('  bounce:', px.shape[1], 'x', px.shape[0])


def build_trees():
    src, heights, ncol = CFG['trees']
    rgb, alpha = load_keyed(src)
    owner, ids = find_figures(alpha, len(heights), by_x=True, min_ratio=CFG.get('trees_min_ratio', 0.2))
    sizes = []
    for i, k in enumerate(ids):
        fig = cut_figure(rgb, alpha, owner, k)
        px = pixel_sprite(fig, (heights[i] - 2) / fig.shape[0], ncol)
        Image.fromarray(px, 'RGBA').save(f'{WORLD}/tree_{i}.png')
        sizes.append([px.shape[1], px.shape[0]])
    path, world = world_meta()
    world.pop('acacias', None)
    world['trees'] = sizes
    json.dump(world, open(path, 'w'), indent=2)
    print('  trees:', sizes)


def build_savepoint():
    """Frame 0 waiting (blue), frame 1 activated (green), like KH's save points."""
    rgb, alpha = load_keyed('savepoint_src.png')
    owner, ids = find_figures(alpha, 1)
    fig = cut_figure(rgb, alpha, owner, ids[0]).astype(np.float64)
    # The generator engraved a pentagram in the middle -- not for this game.
    # Cover the inner circle with plain stone and a soft glow.
    h, w = fig.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy, rx, ry = 0.496 * w, 0.405 * h, 0.15 * w, 0.17 * h
    d = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
    stone = np.median(fig[(fig[..., 3] > 0) & (fig[..., :3].sum(-1) < 240)][:, :3], 0)
    fig[d <= 1.0, :3] = stone
    fig[d <= 0.35, :3] = stone * 0.6 + np.array([120, 200, 255]) * 0.4
    fig = fig.astype(np.uint8)
    px = pixel_sprite(fig, (SAVE_W - 2) / w, 16)
    on = px.copy().astype(np.int32)
    blue = (on[..., 2] > on[..., 0] + 30) & (on[..., 3] > 0)
    on[blue, 1], on[blue, 2] = on[blue, 2], (on[blue, 1] * 0.75).astype(np.int32)
    sheet = np.concatenate([px, on.astype(np.uint8)], 1)
    Image.fromarray(sheet, 'RGBA').save(f'{WORLD}/savepoint.png')
    path, world = world_meta()
    world['savepoint'] = {'frame': [px.shape[1], px.shape[0]]}
    json.dump(world, open(path, 'w'), indent=2)
    print('  savepoint:', px.shape[1], 'x', px.shape[0])


def build_keyhole():
    rgb, alpha = load_keyed('keyhole_src.png')
    owner, ids = find_figures(alpha, 1)
    fig = cut_figure(rgb, alpha, owner, ids[0])
    px = pixel_sprite(fig, (KEYHOLE_H - 2) / fig.shape[0], 20)
    Image.fromarray(px, 'RGBA').save(f'{WORLD}/keyhole.png')
    path, world = world_meta()
    world['keyhole'] = {'size': [px.shape[1], px.shape[0]]}
    json.dump(world, open(path, 'w'), indent=2)
    print('  keyhole:', px.shape[1], 'x', px.shape[0])


def build_props():
    """Shared by every world: the treasure chest (closed, open) and the Star
    Gem. Built with the Pride Lands, loaded once by the game."""
    if os.path.exists(f'{SRC}/chest_src.png'):
        rgb, alpha = load_keyed('chest_src.png')
        owner, ids = find_figures(alpha, 2, by_x=True)
        figs = [cut_figure(rgb, alpha, owner, k) for k in ids]
        f = (CHEST_H - 2) / figs[0].shape[0]                # same scale for both
        pxs = [pixel_sprite(fg, f, 16) for fg in figs]
        cw = max(p.shape[1] for p in pxs) + 2
        ch = max(p.shape[0] for p in pxs) + 1
        cells = []
        for p in pxs:                                       # bottom-centre in one cell
            c = np.zeros((ch, cw, 4), np.uint8)
            c[ch - p.shape[0]:, (cw - p.shape[1]) // 2:(cw - p.shape[1]) // 2 + p.shape[1]] = p
            cells.append(c)
        Image.fromarray(np.concatenate(cells, 1), 'RGBA').save(f'{WORLD}/chest.png')
        path, world = world_meta()
        world['chest'] = {'frame': [cw, ch]}
        json.dump(world, open(path, 'w'), indent=2)
        print('  chest:', cw, 'x', ch)
    if os.path.exists(f'{SRC}/gem_src.png'):
        rgb, alpha = load_keyed('gem_src.png')
        owner, ids = find_figures(alpha, 1)
        fig = cut_figure(rgb, alpha, owner, ids[0])
        px = pixel_sprite(fig, (GEM_H - 2) / fig.shape[0], 12).astype(np.float64)
        # The glow keys out pale; put every pixel on a rich gold ramp by
        # brightness (the dark outline stays dark).
        lum = px[..., :3] @ np.array([0.299, 0.587, 0.114]) / 255.0
        ramp = np.array([[26, 18, 30], [150, 70, 10], [235, 150, 20], [255, 214, 60], [255, 248, 200]], float)
        t = np.clip((lum - 0.25) / 0.7, 0, 1) * (len(ramp) - 1)
        i = np.minimum(np.floor(t).astype(int), len(ramp) - 2)
        gold = ramp[i] + (ramp[i + 1] - ramp[i]) * (t - i)[..., None]
        keep = px[..., 3] > 0
        px[keep, :3] = np.where((lum[keep] < 0.22)[:, None], px[keep, :3], gold[keep])
        Image.fromarray(px.astype(np.uint8), 'RGBA').save(f'{WORLD}/gem.png')
        path, world = world_meta()
        world['gem'] = {'size': [px.shape[1], px.shape[0]]}
        json.dump(world, open(path, 'w'), indent=2)
        print('  gem:', px.shape[1], 'x', px.shape[0])


def share(name, key):
    """Use another world's built sprite as is (the save point, the Keyhole)."""
    import shutil
    other = WORLDS[CFG['shared_from']]['out']
    shutil.copy(f'{other}/{name}', f'{WORLD}/{name}')
    path, world = world_meta()
    world[key] = json.load(open(f'{other}/world.json'))[key]
    json.dump(world, open(path, 'w'), indent=2)
    print(f'  {key}: shared from {CFG["shared_from"]}')


def build_scenery():
    for fn, src, shared in [(build_platform, 'platform.png', None),
                            (build_crumble, CFG.get('crumble_src', 'crumble.png'), None),
                            (build_bounce, 'bounce_src.png', None),
                            (build_trees, CFG['trees'][0], None),
                            (build_savepoint, 'savepoint_src.png', ('savepoint.png', 'savepoint')),
                            (build_keyhole, 'keyhole_src.png', ('keyhole.png', 'keyhole'))]:
        if os.path.exists(f'{SRC}/{src}'):
            fn()
        elif shared and CFG['shared_from']:
            share(*shared)
        else:
            print('  no source', src)
    if CFG.get('beat'):
        build_beat()
    if os.path.exists(f'{SRC}/stage_src.png'):
        build_stage()


PARTS = {'bg': [build_far, build_mid], 'kids': [build_kids], 'sprites': [build_sprites],
         'tiles': [build_tiles], 'scenery': [build_scenery], 'props': [build_props]}


def main():
    global SRC, WORLD, CFG
    args = sys.argv[1:]
    world = 'pride'
    if '--world' in args:
        i = args.index('--world')
        world = args[i + 1]
        del args[i:i + 2]
    CFG = WORLDS[world]
    SRC, WORLD = CFG['src'], CFG['out']
    want = args or [p for p in PARTS if p not in ('kids', 'props') or world == 'pride']
    os.makedirs(WORLD, exist_ok=True)
    print('world:', world)
    for p in want:
        for fn in PARTS[p]:
            fn()


if __name__ == '__main__':
    main()
