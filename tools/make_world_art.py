#!/usr/bin/env python3
"""
Procedural pixel art for the Pride Lands world.

Everything here is drawn by code so it can be regenerated, tweaked and kept
consistent with the kids: large shapes are drawn at 8x and pushed through the
same pixelizer the characters use (hard edges, fixed palette, 1px outline);
small icons are hand-placed pixel maps; backgrounds are drawn at 1x with ordered
(Bayer) dithering, which is how SNES-era skies got smooth gradients out of a
handful of colours.

Writes art/world/pride/*.png and art/world/pride/world.json.

Usage:
    python tools/make_world_art.py
"""

from __future__ import annotations

import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pixelize import downsample, make_palette, finish  # noqa: E402

OUT = 'art/world/pride'
T = 16
W, H = 640, 360
BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0
OUTLINE = (26, 18, 30)


def c(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgba(arr):
    return Image.fromarray(arr.astype(np.uint8), 'RGBA')


def pixmap(rows, colors):
    """Hand-placed pixel art: one character per pixel."""
    h, w = len(rows), max(len(r) for r in rows)
    a = np.zeros((h, w, 4), np.uint8)
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch in colors:
                a[y, x, :3] = c(colors[ch]); a[y, x, 3] = 255
    return a


def from_hires(draw_fn, size, scale=8, ncol=10, outline=OUTLINE):
    """Draw with smooth shapes at `scale`x, then pixelize to `size`."""
    hw, hh = size[0] * scale, size[1] * scale
    im = Image.new('RGBA', (hw, hh), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(im), scale)
    rgb, mask = downsample(im, 1.0 / scale)
    pal = make_palette([(rgb, mask)], ncol)
    return finish(rgb, mask, pal, outline)


def strip(frames):
    h = max(f.shape[0] for f in frames); w = max(f.shape[1] for f in frames)
    out = np.zeros((h, w * len(frames), 4), np.uint8)
    for i, f in enumerate(frames):
        out[h - f.shape[0]:, i * w:i * w + f.shape[1]] = f
    return out, w, h


# =============================================================================
# Tileset
# =============================================================================
# Index order (Phaser tile index = position in the strip):
#   0-7   dirt : top-single, top-left, top-mid, top-right, side-left, side-right, fill, fill-b
#   8-15  rock : same order
#   16-19 ledge: single, left, mid, right   (one-way platforms)

DIRT = dict(base='#a9592c', dark='#8a4523', light='#c26e36', deep='#6e3720', edge='#3b2014',
            g1='#ecc65c', g2='#d3a943', g3='#a8862e', g4='#76702a', root='#5e3219')
ROCK = dict(base='#a08573', dark='#846a5c', light='#bba08b', deep='#5f4a41', edge='#36261f',
            g1='#e1caae', g2='#cdb398', g3='#b0957f', g4='#8f7565', root='#5f4a41')


def terrain_tile(p, rng, top, left, right, speckle=False):
    a = np.zeros((T, T, 4), np.uint8); a[..., 3] = 255
    a[..., :3] = c(p['base'])
    n = rng.random((T, T))
    a[n < 0.13, :3] = c(p['dark'])
    a[(n > 0.88), :3] = c(p['light'])
    if speckle:
        for _ in range(3):
            x, y = rng.integers(1, 14), rng.integers(6, 14)
            a[y, x:x + 2, :3] = c(p['deep'])
    # soft horizontal strata
    for y in (9, 14):
        row = rng.random(T) < 0.5
        a[y, row, :3] = c(p['dark'])
    if top:
        for x in range(T):
            d = 4 + int(rng.integers(0, 3))
            for y in range(d):
                col = p['g1'] if y == 0 else p['g2'] if y < 2 else p['g3'] if y < d - 1 else p['g4']
                a[y, x, :3] = c(col)
            a[d, x, :3] = c(p['root'])
            if rng.random() < 0.28:
                a[0, x, 3] = 0        # ragged grass line
    if left:
        a[:, 0, :3] = c(p['edge']); a[:, 1, :3] = c(p['deep'])
    if right:
        a[:, T - 1, :3] = c(p['edge']); a[:, T - 2, :3] = c(p['deep'])
    if top and left:
        a[0, 0:2, 3] = 0; a[1, 0, 3] = 0
    if top and right:
        a[0, T - 2:, 3] = 0; a[1, T - 1, 3] = 0
    return a


def ledge_tile(rng, left, right):
    a = np.zeros((T, T, 4), np.uint8)
    p = ROCK
    for y in range(7):
        col = p['g1'] if y == 0 else p['g2'] if y == 1 else p['base'] if y < 5 else p['dark']
        a[y, :, :3] = c(col); a[y, :, 3] = 255
    n = rng.random((5, T))
    a[2:7][n < 0.15, :3] = c(p['deep'])
    a[7, 2:T - 2, :3] = c(p['edge']); a[7, 2:T - 2, 3] = 255
    if left:
        a[0:7, 0, 3] = 0; a[0, 1, 3] = 0; a[6, 1, 3] = 0
        a[1:6, 1, :3] = c(p['edge'])
    if right:
        a[0:7, T - 1, 3] = 0; a[0, T - 2, 3] = 0; a[6, T - 2, 3] = 0
        a[1:6, T - 2, :3] = c(p['edge'])
    return a


def make_tiles():
    rng = np.random.default_rng(7)
    tiles = []
    for p in (DIRT, ROCK):
        tiles += [
            terrain_tile(p, rng, True, True, True),
            terrain_tile(p, rng, True, True, False),
            terrain_tile(p, rng, True, False, False),
            terrain_tile(p, rng, True, False, True),
            terrain_tile(p, rng, False, True, False),
            terrain_tile(p, rng, False, False, True),
            terrain_tile(p, rng, False, False, False),
            terrain_tile(p, rng, False, False, False, speckle=True),
        ]
    tiles += [ledge_tile(rng, True, True), ledge_tile(rng, True, False),
              ledge_tile(rng, False, False), ledge_tile(rng, False, True)]
    sheet = np.concatenate(tiles, 1)
    rgba(sheet).save(f'{OUT}/tiles.png')
    return len(tiles)


# =============================================================================
# Parallax backgrounds
# =============================================================================

def gradient_rows(stops, n):
    ys = np.linspace(0, 1, n)
    out = np.zeros((n, 3))
    for i in range(3):
        out[:, i] = np.interp(ys, [s for s, _ in stops], [c(h)[i] for _, h in stops])
    return out


def make_sky():
    stops = [(0.00, '#20174a'), (0.28, '#4e2a6e'), (0.48, '#a2466c'), (0.64, '#e06a4c'),
             (0.78, '#ffa553'), (0.90, '#ffd488'), (1.00, '#ffe8b4')]
    bands = 13
    band_cols = gradient_rows(stops, bands)
    a = np.zeros((H, W, 4), np.uint8); a[..., 3] = 255
    yy, xx = np.mgrid[0:H, 0:W]
    f = yy / (H - 1) * (bands - 1)
    i = np.floor(f).astype(int); frac = f - i
    pick = np.where(frac > BAYER[yy % 4, xx % 4], np.minimum(i + 1, bands - 1), i)
    a[..., :3] = band_cols[pick]

    # The sun, low and huge -- the opening of the film in one shape.
    cx, cy, r = 452, 258, 56
    d = np.hypot(xx - cx, yy - cy)
    halo = (d < r + 20) & (d >= r)
    t = (d - r) / 20.0
    a[halo & (t < BAYER[yy % 4, xx % 4] * 1.1), :3] = c('#ffd27c')
    a[d < r, :3] = c('#ffd884')
    a[d < r - 4, :3] = c('#fff1c2')

    # Long cloud streaks across the sun.
    def streak(x0, x1, y, th, col, density):
        for x in range(x0, x1):
            e = min(x - x0, x1 - x) / 22.0
            for dy in range(-th, th + 1):
                if abs(dy) / (th + 0.01) < min(1, e) and BAYER[(y + dy) % 4, x % 4] < density:
                    a[y + dy, x % W, :3] = c(col)
    streak(300, 600, 236, 2, '#f08d66', 0.85)
    streak(360, 640, 248, 1, '#d8606a', 0.9)
    streak(40, 300, 196, 2, '#c4566c', 0.7)
    streak(470, 700, 280, 1, '#f29a68', 0.8)
    rgba(a).save(f'{OUT}/sky.png')


def periodic(x, Wd, terms):
    return sum(amp * np.sin(2 * math.pi * k * x / Wd + ph) for amp, k, ph in terms)


def make_far():
    Wd = 1280
    a = np.zeros((H, Wd, 4), np.uint8)
    xs = np.arange(Wd)
    prof = (238 + periodic(xs, Wd, [(14, 2, 0.3), (8, 5, 1.1), (4, 11, 2.0)])).astype(int)
    body, rim, haze = c('#8b4569'), c('#ad5f7b'), c('#9b5072')
    for x in xs:
        y0 = prof[x]
        a[y0:, x, :3] = body; a[y0:, x, 3] = 255
        a[y0:y0 + 2, x, :3] = rim
    # Pride Rock: a mesa with the famous jutting promontory.
    im = Image.fromarray(a, 'RGBA'); d = ImageDraw.Draw(im)
    pr = [(760, 300), (788, 236), (820, 214), (858, 200), (905, 192), (985, 190), (1012, 196),
          (996, 203), (940, 207), (912, 222), (900, 250), (930, 300)]
    d.polygon(pr, fill=c('#7a3a5f') + (255,))
    d.line([(858, 200), (905, 192), (985, 190), (1012, 196)], fill=c('#b8657f') + (255,), width=2)
    a = np.asarray(im).copy()
    # haze toward the horizon
    yy, xx = np.mgrid[0:H, 0:Wd]
    m = (a[..., 3] > 0) & (yy > 300) & (BAYER[yy % 4, xx % 4] < (yy - 300) / 60.0)
    a[m, :3] = haze
    rgba(a).save(f'{OUT}/far.png')


def make_mid():
    Wd = 1280
    a = np.zeros((H, Wd, 4), np.uint8)
    xs = np.arange(Wd)
    prof = (290 + periodic(xs, Wd, [(10, 3, 0.5), (6, 7, 2.0), (3, 13, 0.9)])).astype(int)
    body, rim = c('#5a2a44'), c('#713756')
    rng = np.random.default_rng(3)
    for x in xs:
        y0 = prof[x]
        a[y0:, x, :3] = body; a[y0:, x, 3] = 255
        a[y0, x, :3] = rim
        if rng.random() < 0.35:                       # dry grass tufts
            hgt = int(rng.integers(1, 4))
            a[y0 - hgt:y0, x, :3] = rim; a[y0 - hgt:y0, x, 3] = 255
    im = Image.fromarray(a, 'RGBA'); d = ImageDraw.Draw(im)
    tree = c('#3c1a2f') + (255,)
    for tx, s in [(150, 1.0), (520, 0.72), (780, 1.2), (1110, 0.85)]:
        base = prof[tx]
        top = base - int(64 * s)
        d.line([(tx, base), (tx + int(4 * s), top + int(14 * s))], fill=tree, width=max(2, int(4 * s)))
        d.line([(tx + int(3 * s), top + int(22 * s)), (tx - int(16 * s), top + 6)], fill=tree, width=max(2, int(3 * s)))
        d.line([(tx + int(4 * s), top + int(16 * s)), (tx + int(22 * s), top + 4)], fill=tree, width=max(2, int(3 * s)))
        d.ellipse([tx - int(46 * s), top - int(4 * s), tx + int(50 * s), top + int(12 * s)], fill=tree)
        d.ellipse([tx - int(26 * s), top - int(13 * s), tx + int(28 * s), top + int(2 * s)], fill=tree)
    rgba(np.asarray(im)).save(f'{OUT}/mid.png')


# =============================================================================
# Props (in-level decoration, drawn behind the player)
# =============================================================================

def make_acacia():
    def draw(d, s):
        trunk = c('#6b3e26') + (255,); trunk_l = c('#8a5434') + (255,)
        d.polygon([(44 * s, 74 * s), (52 * s, 74 * s), (50 * s, 40 * s), (47 * s, 40 * s)], fill=trunk)
        d.line([(48 * s, 44 * s), (30 * s, 26 * s)], fill=trunk, width=3 * s)
        d.line([(49 * s, 42 * s), (64 * s, 24 * s)], fill=trunk, width=3 * s)
        d.line([(49 * s, 50 * s), (49 * s, 74 * s)], fill=trunk_l, width=1 * s)
        dark, mid, lite = c('#55611f') + (255,), c('#728131') + (255,), c('#93a240') + (255,)
        d.ellipse([4 * s, 16 * s, 92 * s, 34 * s], fill=dark)
        d.ellipse([10 * s, 10 * s, 84 * s, 28 * s], fill=mid)
        d.ellipse([22 * s, 6 * s, 66 * s, 20 * s], fill=lite)
    rgba(from_hires(draw, (96, 76), ncol=8)).save(f'{OUT}/acacia.png')


def make_bush():
    def draw(d, s):
        for (x, y, r, col) in [(8, 12, 7, '#a8862e'), (16, 9, 8, '#d3a943'), (25, 12, 7, '#a8862e'),
                               (15, 13, 6, '#ecc65c')]:
            d.ellipse([(x - r) * s, (y - r) * s, (x + r) * s, (y + r) * s], fill=c(col) + (255,))
        for x in range(3, 30, 3):
            d.line([(x * s, 16 * s), ((x + 1) * s, 3 * s)], fill=c('#ecc65c') + (255,), width=s)
    rgba(from_hires(draw, (32, 18), ncol=6)).save(f'{OUT}/bush.png')


# =============================================================================
# Shadow Heartless
# =============================================================================

def shadow_frame(phase, walk):
    def draw(d, s):
        k = lambda v: int(v * s)
        body = c('#1b1424') + (255,); rim = c('#3d2f57') + (255,)
        eye = c('#ffd54a') + (255,); glint = c('#fff4b8') + (255,)
        bob = math.sin(phase * 2 * math.pi) * 0.8
        sw = math.sin(phase * 2 * math.pi) * (4 if walk else 0.6)
        # legs (bent, crouched)
        for side, off in ((-1, sw), (1, -sw)):
            hx = 13 + side * 3
            d.line([(k(hx), k(19 + bob)), (k(hx - 3 + off * 0.5), k(23)), (k(hx + off), k(26.5))],
                   fill=body, width=k(2.2))
        # body
        d.ellipse([k(6), k(12 + bob), k(21), k(23 + bob)], fill=body)
        d.ellipse([k(7), k(12.5 + bob), k(13), k(17 + bob)], fill=rim)
        d.ellipse([k(7.5), k(13 + bob), k(20), k(23 + bob)], fill=body)
        # arm hanging forward, with claws
        d.line([(k(18), k(15 + bob)), (k(21.5 - sw * 0.3), k(21 + bob)), (k(22 - sw * 0.3), k(24))],
               fill=body, width=k(1.8))
        # head
        d.ellipse([k(10), k(4 + bob), k(25), k(15.5 + bob)], fill=body)
        d.ellipse([k(11), k(4.5 + bob), k(16), k(8.5 + bob)], fill=rim)
        # antennae, curling back
        w = math.sin(phase * 2 * math.pi + 1) * 1.2
        d.line([(k(15), k(5 + bob)), (k(11 + w), k(1)), (k(7 + w), k(1.5)), (k(6 + w), k(4))],
               fill=body, width=k(1.6), joint='curve')
        d.line([(k(19), k(5 + bob)), (k(17 - w), k(0.5)), (k(13 - w), k(0)), (k(12 - w), k(2.4))],
               fill=body, width=k(1.6), joint='curve')
        # eyes: the yellow is the whole identity of a Shadow
        d.ellipse([k(18.2), k(7.4 + bob), k(21.6), k(11.6 + bob)], fill=eye)
        d.ellipse([k(21.8), k(7.8 + bob), k(24.4), k(11.4 + bob)], fill=eye)
        d.ellipse([k(19), k(8 + bob), k(20.2), k(9.4 + bob)], fill=glint)
    return from_hires(draw, (28, 28), ncol=6, outline=(10, 6, 16))


def make_shadow():
    frames = [shadow_frame(0.0, False), shadow_frame(0.5, False),
              shadow_frame(0.0, True), shadow_frame(0.25, True),
              shadow_frame(0.5, True), shadow_frame(0.75, True)]
    puddle = pixmap([
        '...oooooooooooo...',
        '.oobbbbbbbbbbbboo.',
        'obbbbbbbyy.yybbbbo',
        '.oobbbbbbbbbbbboo.',
        '...oooooooooooo...',
    ], {'o': '#0a0610', 'b': '#1b1424', 'y': '#ffd54a'})
    # The puddle is the LAST FRAME of the same sheet, on the same 28x28 canvas
    # with its bottom on the feet line. Swapping to a differently sized texture
    # moved the physics body 23px below the feet and dropped Shadows out of
    # the world the moment they sank.
    fw, fh = frames[0].shape[1], frames[0].shape[0]
    pf = np.zeros((fh, fw, 4), np.uint8)
    ph, pw = puddle.shape[:2]
    x0 = (fw - pw) // 2
    pf[fh - ph - 1:fh - 1, x0:x0 + pw] = puddle
    frames.append(pf)
    sheet, fw, fh = strip(frames)
    rgba(sheet).save(f'{OUT}/shadow.png')
    return fw, fh, len(frames)


# =============================================================================
# Simba (placeholder until a generated sprite replaces it)
# =============================================================================

def simba_frame(phase, mode):
    def draw(d, s):
        k = lambda v: int(v * s)
        fur, fur_d = c('#e3a24a') + (255,), c('#c4832f') + (255,)
        belly, muzzle = c('#f6d18c') + (255,), c('#f8dda0') + (255,)
        tuft, ear_in = c('#a8452a') + (255,), c('#b8692e') + (255,)
        dark = c('#3a2418') + (255,)
        sw = math.sin(phase * 2 * math.pi) * 3.2
        stretch = 3 if mode == 'pounce' else 0
        # tail
        tw = math.sin(phase * 2 * math.pi + 1.5) * 2
        d.line([(k(9), k(19)), (k(4), k(15 + tw)), (k(3), k(9 + tw))], fill=fur_d, width=k(1.6), joint='curve')
        d.ellipse([k(1), k(6 + tw), k(5.5), k(11 + tw)], fill=tuft)
        # back legs
        for x, off in ((11, sw), (14, -sw)):
            d.rounded_rectangle([k(x + off * 0.4 - stretch * 0.6), k(20), k(x + 3 + off * 0.4 - stretch * 0.6), k(30.5)],
                                radius=k(1.4), fill=fur_d if off > 0 else fur)
        # front legs
        for x, off in ((24, -sw), (27, sw)):
            d.rounded_rectangle([k(x + off * 0.4 + stretch), k(20), k(x + 3 + off * 0.4 + stretch), k(30.5)],
                                radius=k(1.4), fill=fur_d if off > 0 else fur)
        # body
        d.ellipse([k(7 - stretch * 0.5), k(14), k(31 + stretch), k(25)], fill=fur)
        d.ellipse([k(12), k(19), k(28 + stretch), k(25)], fill=belly)
        # head
        hx = 30 + stretch
        d.ellipse([k(hx - 7), k(5), k(hx + 6), k(18)], fill=fur)
        d.ellipse([k(hx - 6), k(3.5), k(hx - 1.5), k(8)], fill=fur_d)
        d.ellipse([k(hx - 5), k(4.5), k(hx - 2.5), k(7)], fill=ear_in)
        d.polygon([(k(hx - 3), k(5)), (k(hx), k(1.5)), (k(hx + 1), k(5.5)), (k(hx + 3), k(3)), (k(hx + 2), k(6.5))], fill=tuft)
        d.ellipse([k(hx), k(10), k(hx + 9), k(17)], fill=muzzle)
        d.polygon([(k(hx + 7), k(10.2)), (k(hx + 9.5), k(10.6)), (k(hx + 8.2), k(12.4))], fill=dark)
        d.ellipse([k(hx + 1.4), k(8), k(hx + 3.6), k(11)], fill=dark)
        d.line([(k(hx + 4), k(14.6)), (k(hx + 7.5), k(14.2))], fill=dark, width=max(1, k(0.5)))
    return from_hires(draw, (44, 32), ncol=10)


def make_simba():
    frames = [simba_frame(p, 'walk') for p in (0, 0.25, 0.5, 0.75)] + [simba_frame(0.1, 'pounce')]
    sheet, fw, fh = strip(frames)
    rgba(sheet).save(f'{OUT}/simba.png')
    return fw, fh, len(frames)


# =============================================================================
# Keyblade, swoosh, pickups, save point, keyhole, effects
# =============================================================================

KEYBLADE = [
    '..OOOOOOO.....................',
    '.OGGGGGGGO....................',
    '.OGgOOOgGO....................',
    '.OGOdddOGOOOOOOOOOOOOOOOOOO...',
    'OOGOdddOGSSSSSSSSSSSSSSSSSSO..',
    'OGGOdddOGsssssssssssssssssszO.',
    'OOGOdddOGOOOOOOOOOOOOzsssszOO.',
    '.OGgOOOgGO..........OzssszO...',
    '.OGGGGGGGO..........OsOOOsO...',
    '..OOOOOOO...........OO...OO...',
    '...O..........................',
    '..OkO.........................',
    '.OkkkO........................',
    '..OOO.........................',
]
KB_COLORS = {'O': '#1e1a2e', 'G': '#f2c64a', 'g': '#b8862a', 'd': '#2e2f6a',
             'S': '#f2f5fb', 's': '#b7bfce', 'z': '#7c8597', 'k': '#141020'}


def make_keyblade():
    a = pixmap(KEYBLADE, KB_COLORS)
    rgba(a).save(f'{OUT}/keyblade.png')
    return a.shape[1], a.shape[0]


def make_swoosh():
    S = 6
    R = 30
    size = 2 * R + 6
    im = Image.new('RGBA', (size * S, size * S), (0, 0, 0, 0))
    a = np.zeros((size * S, size * S, 4), np.float64)
    yy, xx = np.mgrid[0:size * S, 0:size * S]
    cx = cy = size * S / 2
    ang = np.degrees(np.arctan2(yy - cy, xx - cx))           # 0 = right, +90 = down
    d = np.hypot(xx - cx, yy - cy) / S
    a0, a1 = -110.0, 60.0
    t = np.clip((ang - a0) / (a1 - a0), 0, 1)
    inside = (ang >= a0) & (ang <= a1)
    outer = R
    inner = R - 2 - 7 * np.sin(t * math.pi)                  # crescent: thick in the middle
    band = inside & (d <= outer) & (d >= inner)
    core = band & (d >= inner + 1.6) & (d <= outer - 1.2)
    a[band] = (*c('#9fe3ff'), 255)
    a[core] = (*c('#ffffff'), 255)
    im = Image.fromarray(a.astype(np.uint8), 'RGBA').resize((size, size), Image.NEAREST)
    im.save(f'{OUT}/swoosh.png')
    return size


def make_icons():
    heart = [
        '.OOO...OOO.',
        'ORRRO.ORRRO',
        'ORWRRORRRRO',
        'ORWRRRRRRRO',
        'ORRRRRRRRRO',
        '.ORRRRRRRO.',
        '..ORRRRRO..',
        '...ORRRO...',
        '....ORO....',
        '.....O.....',
    ]
    full = pixmap(heart, {'O': '#2a1220', 'R': '#e8364a', 'W': '#ffb3ba'})
    empty = pixmap(heart, {'O': '#2a1220', 'R': '#4a2a3a', 'W': '#5e3a4c'})
    rgba(np.concatenate([full, empty], 1)).save(f'{OUT}/heart.png')

    munny = pixmap([
        '..OOOO..',
        '.OYYYYO.',
        'OYWWYYYO',
        'OYWYYYYO',
        'OYYYYYgO',
        'OYYYYggO',
        '.OYggggO',
        '..OOOO..',
    ], {'O': '#5a3510', 'Y': '#ffd23f', 'W': '#fff6c8', 'g': '#d99a1c'})
    rgba(munny).save(f'{OUT}/munny.png')

    small_heart = pixmap([
        '.PP.PP.',
        'PWPPPPP',
        'PPPPPPP',
        '.PPPPP.',
        '..PPP..',
        '...P...',
    ], {'P': '#ff7fb2', 'W': '#ffd6e8'})
    rgba(small_heart).save(f'{OUT}/heart_small.png')

    sparkle = pixmap(['.W.', 'WWW', '.W.'], {'W': '#ffffff'})
    rgba(sparkle).save(f'{OUT}/sparkle.png')

    star = pixmap([
        '...W...',
        '...W...',
        '.W.W.W.',
        'WWWWWWW',
        '.W.W.W.',
        '...W...',
        '...W...',
    ], {'W': '#ffffff'})
    rgba(star).save(f'{OUT}/hitstar.png')


def make_savepoint():
    out = []
    for on in (False, True):
        ring, core, glow = (('#7cffb8', '#2fd88a', '#c8ffe2') if on else ('#7d93d6', '#3f538e', '#a9b8e8'))
        def draw(d, s, ring=ring, core=core, glow=glow):
            k = lambda v: int(v * s)
            d.ellipse([k(1), k(1), k(39), k(11)], fill=c(ring) + (255,))
            d.ellipse([k(5), k(3), k(35), k(9)], fill=c(core) + (255,))
            d.ellipse([k(11), k(4.5), k(29), k(7.5)], fill=c(glow) + (255,))
        out.append(from_hires(draw, (40, 12), ncol=5, outline=(16, 22, 40)))
    sheet, fw, fh = strip(out)
    rgba(sheet).save(f'{OUT}/savepoint.png')
    return fw, fh


def make_keyhole():
    def draw(d, s):
        k = lambda v: int(v * s)
        for grow, col in ((3.0, '#ff9a3c'), (1.5, '#ffd25a'), (0.0, '#fffbe8')):
            d.ellipse([k(8 - grow), k(4 - grow), k(24 + grow), k(20 + grow)], fill=c(col) + (255,))
            d.polygon([(k(11 - grow), k(16)), (k(21 + grow), k(16)), (k(25 + grow), k(44 + grow * 0.5)),
                       (k(7 - grow), k(44 + grow * 0.5))], fill=c(col) + (255,))
    rgba(from_hires(draw, (32, 48), ncol=4, outline=(90, 40, 20))).save(f'{OUT}/keyhole.png')


def main():
    os.makedirs(OUT, exist_ok=True)
    ntiles = make_tiles()
    make_sky(); make_far(); make_mid()
    make_acacia(); make_bush()
    sw, sh, sn = make_shadow()
    mw, mh, mn = make_simba()
    kw, kh = make_keyblade()
    swoosh = make_swoosh()
    make_icons()
    pw, ph = make_savepoint()
    make_keyhole()
    meta = {
        'tile': T, 'tiles': ntiles,
        'shadow': {'frame': [sw, sh], 'frames': sn},
        'simba': {'frame': [mw, mh], 'frames': mn},
        'keyblade': {'size': [kw, kh], 'grip': [5, 5]},
        'swoosh': {'size': [swoosh, swoosh]},
        'savepoint': {'frame': [pw, ph]},
    }
    json.dump(meta, open(f'{OUT}/world.json', 'w'), indent=2)
    # Sprite sheet layouts the game reads. tools/build_gen_art.py overrides an
    # entry when a generated sprite replaces the procedural one.
    sprites = {
        'shadow': {'frame': [sw, sh], 'body': [14, 18],
                   'anims': {'walk': [2, 5], 'idle': [0, 1]}, 'puddle': sn - 1, 'source': 'procedural'},
        'simba': {'frame': [mw, mh], 'anims': {'walk': [0, 3]}, 'pounce': 4, 'source': 'procedural'},
    }
    path = f'{OUT}/sprites.json'
    if os.path.exists(path):
        old = json.load(open(path))
        for k, v in old.items():
            if v.get('source') == 'generated':
                sprites[k] = v          # never clobber a generated sprite
    json.dump(sprites, open(path, 'w'), indent=2)
    print(json.dumps(meta))


if __name__ == '__main__':
    main()
