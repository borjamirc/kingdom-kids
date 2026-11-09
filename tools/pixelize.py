#!/usr/bin/env python3
"""
HD keyed sprite sheets -> real pixel art.

Reads the normalised sheets from art/sheets/ (output of process_art.py) and the
hand-tuned sizes in art/pixel_spec.json, and writes true pixel art drawn at 1:1
for the 640x360 game screen:

    art/pixel/<Char>/idle.png  run.png  jump.png  attack.png
    art/pixel/portraits/<Char>.png
    art/pixel/manifest.json

"Real" pixel art here means: every sprite is downsampled to the exact size it
will be drawn at (no runtime scaling, so all pixels are the same size on
screen), edges are hard (no partial alpha), each kid uses one fixed palette
across all of their animations, and the silhouette gets the 1px dark outline
that makes SNES sprites read against busy backgrounds.

The attack is a real Keyblade slash when one has been generated (a strip of
frames in art/gen/attack/<Char>.png, see tools/build_gen_art.py): the kid's arms
and the blade move together. Without one, it falls back to frame 3 of the old
fireball sheet with the orb deleted, and the game draws a Keyblade over it.

Sizes come from 'height' in the spec: the kid's standing height in pixels on
the idle animation. Per-action multipliers stay relative to that.

Usage:
    python tools/pixelize.py
"""

from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image
from scipy import ndimage

SPEC = 'art/pixel_spec.json'
SHEETS = 'art/sheets'
PORTRAITS = 'art/portraits'
OUT = 'art/pixel'
ANIMS = ['idle', 'run', 'jump', 'attack']
ST8 = np.ones((3, 3), bool)
CROSS = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool)
PAD = 1


def gen_attack_frames(char, spec):
    """Generated Keyblade slash, if there is one: a horizontal strip of RGBA
    frames of equal size, background removed, every frame's feet at the same
    'anchor' point (see tools/build_gen_art.py). Returns (frames, meta)."""
    p = f"{spec.get('attackSource', 'art/gen/attack')}/{char}.png"
    if not os.path.exists(p):
        return None
    meta = json.load(open(p.replace('.png', '.json')))
    im = Image.open(p).convert('RGBA')
    fw = meta['frame'][0]
    return [im.crop((i * fw, 0, (i + 1) * fw, im.height)) for i in range(im.width // fw)], meta


def body_height(im, anchor):
    """Kid's height in a slash frame, ignoring the Keyblade: measured only
    behind the feet centre (the blade is held in front in the ready pose)."""
    a = np.asarray(im)[..., 3] >= 128
    ax, ay = anchor
    rows = np.where(a[:, :ax + 1].any(1))[0]
    return int(ay - rows.min() + 1)


def figure_height(im):
    a = np.asarray(im)[..., 3] >= 128
    lab, n = ndimage.label(a, structure=ST8)
    if not n:
        return 1
    sz = np.bincount(lab.ravel()); sz[0] = 0
    ys, _ = np.where(lab == int(np.argmax(sz)))
    return int(ys.max() - ys.min() + 1)


def hd_frames(char, anim, manifest, attack_frame):
    cw, ch = manifest[char]['cell']
    im = Image.open(f'{SHEETS}/{char}/{anim}.png').convert('RGBA')
    n = im.width // cw
    idx = [attack_frame] if anim == 'attack' else range(n)
    out = []
    for i in idx:
        f = im.crop((i * cw, 0, (i + 1) * cw, ch))
        if anim == 'attack':
            f = keep_main_body(f)
        out.append(f)
    return out


def keep_main_body(im):
    """Delete everything not attached to the kid: the thrown orb and its dashes."""
    a = np.asarray(im).copy()
    solid = a[..., 3] >= 128
    lab, n = ndimage.label(solid, structure=ST8)
    if n <= 1:
        return im
    sizes = np.bincount(lab.ravel()); sizes[0] = 0
    body = lab == int(np.argmax(sizes))
    keep = ndimage.binary_dilation(body, ST8, iterations=3)   # keep the soft fringe
    a[~keep] = 0
    return Image.fromarray(a, 'RGBA')


def downsample(im, factor):
    """Premultiplied area downsample to the final on-screen size."""
    a = np.asarray(im).astype(np.float64)
    al = a[..., 3:4] / 255.0
    pm = np.concatenate([a[..., :3] * al, al * 255], -1)
    w, h = im.size
    nw, nh = max(1, round(w * factor)), max(1, round(h * factor))
    s = np.asarray(Image.fromarray(np.clip(pm, 0, 255).astype(np.uint8), 'RGBA')
                   .resize((nw, nh), Image.BOX)).astype(np.float64)
    A = s[..., 3] / 255.0
    mask = A >= 0.45
    rgb = np.where(A[..., None] > 1e-3, s[..., :3] / np.maximum(A, 1e-3)[..., None], 0)
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    lab, n = ndimage.label(mask)
    if n:
        sz = np.bincount(lab.ravel()); sz[0] = 0
        mask &= sz[lab] >= 3          # orphan pixels read as dirt at this size
    return rgb, mask


def make_palette(frames, ncol):
    pix = np.concatenate([rgb[m] for rgb, m in frames], 0)
    img = Image.fromarray(pix.reshape(1, -1, 3).astype(np.uint8), 'RGB')
    return img.quantize(colors=ncol, method=Image.Quantize.MEDIANCUT, kmeans=4)


def finish(rgb, mask, pal, outline):
    q = np.asarray(Image.fromarray(rgb, 'RGB')
                   .quantize(palette=pal, dither=Image.Dither.NONE).convert('RGB'))
    ring = ndimage.binary_dilation(mask, CROSS) & ~mask
    out = np.zeros((*mask.shape, 4), np.uint8)
    out[mask, :3] = q[mask]; out[mask, 3] = 255
    out[ring, :3] = outline; out[ring, 3] = 255
    return out


def measure(px, ax=None):
    """Feet anchor of the main figure: lowest row, centred on the feet.
    A generated slash frame passes its known feet centre in 'ax': guessing it
    from the lowest rows fails when the blade sweeps down past the knees."""
    solid = px[..., 3] > 0
    lab, n = ndimage.label(solid, structure=ST8)
    sizes = np.bincount(lab.ravel()); sizes[0] = 0
    fig = lab == int(np.argmax(sizes))
    ys, xs = np.where(fig)
    y0, y1 = int(ys.min()), int(ys.max())
    if ax is None:
        band = fig[y1 - max(1, int((y1 - y0 + 1) * 0.25)) + 1:y1 + 1]
        fc = np.where(band.any(0))[0]
        ax = int((fc.min() + fc.max()) // 2)
    else:
        y1 = int(np.where(solid[:, :ax + 1].any(1))[0].max())   # back foot, not a blade tip
    cys, cxs = np.where(solid)
    return dict(ax=ax, by=y1, x0=int(cxs.min()), x1=int(cxs.max()),
                y0=int(cys.min()), y1=int(cys.max()), fig=fig,
                fw=int(xs.max() - xs.min() + 1), fh=y1 - y0 + 1)


def hand_point(px, m):
    """Front-most point of the arms in the lunge pose, where the Keyblade grip goes."""
    fig = m['fig']
    top, bot = m['by'] - m['fh'] + 1, m['by']
    lo, hi = top + int(m['fh'] * 0.22), top + int(m['fh'] * 0.70)
    band = fig[lo:hi + 1]
    cols = np.where(band.any(0))[0]
    hx = int(cols.max())
    rows = np.where(band[:, hx])[0]
    hy = lo + int(rows.mean())
    return hx - 2, hy          # grip sits just inside the fingertips


def main():
    spec = json.load(open(SPEC))
    hd = json.load(open(f'{SHEETS}/manifest.json'))
    k = spec['internal'][0] / spec['design'][0]
    outline = tuple(spec['outline'])
    os.makedirs(f'{OUT}/portraits', exist_ok=True)

    manifest = {}
    real_h = {}
    for char, cfg in spec['characters'].items():
        # Scale that puts the idle figure at the requested height (the outline
        # adds a pixel top and bottom, so aim 2px short).
        hd_idle = hd[char]['figure'][1]
        base = (cfg['height'] - 2) / (hd_idle * cfg['anims'].get('idle', 1.0))
        raw = {}
        gen = gen_attack_frames(char, spec)
        gen_ax = None
        for anim in ANIMS:
            mult = cfg['anims'].get(anim, 1.0)
            if anim == 'attack' and gen:
                frames, gmeta = gen
                # Ready stance (frame 0) a touch shorter than standing upright.
                ratio = cfg.get('attackReadyRatio', spec.get('attackReadyRatio', 0.96))
                target = (cfg['height'] - 2) * ratio
                f = target / body_height(frames[0], gmeta['anchor'])
                raw[anim] = [downsample(fr, f) for fr in frames]
                gen_ax = int(gmeta['anchor'][0] * f)
            else:
                f = base * mult
                raw[anim] = [downsample(fr, f) for fr in hd_frames(char, anim, hd, spec['attackFrame'])]
        pal = make_palette([fr for frs in raw.values() for fr in frs], spec['palette'])
        done = {a: [finish(rgb, msk, pal, outline) for rgb, msk in frs] for a, frs in raw.items()}
        meas = {a: [measure(px, gen_ax if a == 'attack' else None) for px in frs]
                for a, frs in done.items()}

        # One cell for the whole character, feet on a shared anchor.
        L = R = T = B = 0
        for a in ANIMS:
            for m in meas[a]:
                L = max(L, m['ax'] - m['x0']); R = max(R, m['x1'] - m['ax'])
                T = max(T, m['by'] - m['y0']); B = max(B, m['y1'] - m['by'])
        cw, chh = L + R + 1 + 2 * PAD, T + B + 1 + 2 * PAD
        ax, ay = PAD + L, PAD + T

        os.makedirs(f'{OUT}/{char}', exist_ok=True)
        for a in ANIMS:
            sheet = np.zeros((chh, cw * len(done[a]), 4), np.uint8)
            for i, (px, m) in enumerate(zip(done[a], meas[a])):
                crop = px[m['y0']:m['y1'] + 1, m['x0']:m['x1'] + 1]
                ox = i * cw + ax - (m['ax'] - m['x0'])
                oy = ay - (m['by'] - m['y0'])
                h, w = crop.shape[:2]
                region = sheet[oy:oy + h, ox:ox + w]
                sel = crop[..., 3] > 0
                region[sel] = crop[sel]
            Image.fromarray(sheet, 'RGBA').save(f'{OUT}/{char}/{a}.png')

        idle_fig = max(meas['idle'], key=lambda m: m['fh'])
        hx, hy = hand_point(done['attack'][0], meas['attack'][0])
        ma = meas['attack'][0]
        # Keyblade tip in the ready pose: the highest opaque pixel of frame 0 in
        # front of the kid, where the beam starts when the kid seals the Keyhole.
        a0 = done['attack'][0][..., 3] > 0
        a0[:, :ma['ax'] + max(3, idle_fig['fw'] // 2)] = False     # past the face
        tys, txs = np.where(a0)
        ti = int(np.argmin(tys))
        tip = [int(txs[ti]) - ma['ax'], int(tys[ti]) - ma['by']]
        real_h[char] = idle_fig['fh']
        manifest[char] = {
            'cell': [cw, chh],
            'anchor': [ax, ay],
            'animations': {a: len(done[a]) for a in ANIMS},
            'figure': [idle_fig['fw'], idle_fig['fh']],
            # Keyblade grip in the lunge frame, relative to the feet anchor.
            'hand': [hx - ma['ax'], hy - ma['by']],
            'bladeTip': tip,
            'generatedAttack': bool(gen),
            # How far the Keyblade reaches in front of the feet on the strike
            # frame (frame 2 of a generated slash) -- the game's hit box depth.
            'attackReach': int(meas['attack'][min(2, len(meas['attack']) - 1)]['x1']
                               - meas['attack'][min(2, len(meas['attack']) - 1)]['ax']),
            'colors': len(pal.getpalette()) // 3,
        }
        print(f'{char:10} cell {cw}x{chh}  stands {idle_fig["fh"]}px  hand {manifest[char]["hand"]}')

    # Portraits: true relative sizes, so the menu shows the cast as it plays.
    maxh, maxw = spec['portraitMaxHeight'], spec['portraitMaxWidth']
    src = {c: Image.open(f'{PORTRAITS}/{c}.png').convert('RGBA') for c in spec['characters']}
    K = min(min(maxh / real_h[c], maxw / (real_h[c] * src[c].width / src[c].height)) for c in src)
    for c, im in src.items():
        target_h = K * real_h[c]
        f = target_h / im.height
        rgb, msk = downsample(im, f)
        pal = make_palette([(rgb, msk)], spec['palette'])
        px = finish(rgb, msk, pal, outline)
        Image.fromarray(px, 'RGBA').crop(Image.fromarray(px, 'RGBA').getbbox()).save(f'{OUT}/portraits/{c}.png')
        manifest[c]['portrait'] = list(Image.open(f'{OUT}/portraits/{c}.png').size)

    with open(f'{OUT}/manifest.json', 'w') as fh:
        json.dump(manifest, fh, indent=2)
    print('wrote', f'{OUT}/manifest.json')


if __name__ == '__main__':
    main()
