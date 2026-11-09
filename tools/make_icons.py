#!/usr/bin/env python3
"""
Home-screen icons for the web app: the golden Keyhole on a sunset-to-night
sky, scaled up by whole numbers so the pixel art stays crisp.

Writes icons/icon-180.png (iPhone home screen), icon-192.png and icon-512.png
(web app manifest). iOS rounds the corners itself, so the icons are square
and fully opaque.

Usage:
    python tools/make_icons.py
"""

import os

import numpy as np
from PIL import Image

KEYHOLE = 'art/world/pride/keyhole.png'
OUT = 'icons'
TOP, BOTTOM = np.array([28, 18, 62]), np.array([226, 108, 76])     # night -> sunset
BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0


def sky(size, px):
    """Banded gradient with ordered dithering, drawn on a coarse pixel grid."""
    n = size // px
    yy, xx = np.mgrid[0:n, 0:n]
    bands = 7
    f = yy / (n - 1) * (bands - 1)
    i = np.floor(f).astype(int)
    pick = np.where(f - i > BAYER[yy % 4, xx % 4], np.minimum(i + 1, bands - 1), i)
    cols = np.array([TOP + (BOTTOM - TOP) * k / (bands - 1) for k in range(bands)])
    img = cols[pick].astype(np.uint8)
    rng = np.random.default_rng(5)
    for _ in range(n // 3):                                   # a few stars up top
        y, x = rng.integers(0, n // 2), rng.integers(0, n)
        img[y, x] = (255, 240, 200)
    return Image.fromarray(img, 'RGB').resize((n * px, n * px), Image.NEAREST)


def icon(size):
    key = Image.open(KEYHOLE).convert('RGBA')
    scale = max(1, round(size * 0.78 / key.height))
    if key.height * scale > size * 0.86:
        scale -= 1
    k = key.resize((key.width * scale, key.height * scale), Image.NEAREST)
    bg = sky(size, scale).resize((size, size), Image.NEAREST).convert('RGBA')
    bg.alpha_composite(k, ((size - k.width) // 2, (size - k.height) // 2))
    return bg.convert('RGB')


def main():
    os.makedirs(OUT, exist_ok=True)
    for s in (180, 192, 512):
        icon(s).save(f'{OUT}/icon-{s}.png')
        print('wrote', f'{OUT}/icon-{s}.png')


if __name__ == '__main__':
    main()
