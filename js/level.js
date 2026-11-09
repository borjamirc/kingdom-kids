/* ---------------------------------------------------------------------------
 * Text level -> tile grid + object list.
 *
 * A level is a plain text file, one character per 16x16 tile, so it can be
 * edited in Notepad. Lines starting with '#' are comments. The terrain letters
 * only say WHAT a tile is; which grass edge, corner or rock side to draw is
 * worked out here from the neighbours, so nobody has to type tile numbers.
 * ------------------------------------------------------------------------- */
window.GAME = window.GAME || {};

GAME.Level = {
  // Tileset layout. The defaults are the old one-row procedural strip
  // (tools/make_world_art.py); a generated tileset (tools/build_gen_art.py
  // tiles) describes itself in world.json and replaces them via configure().
  TERRAIN: { G: 0, R: 8 },        // base index of each terrain set
  KIND_STRIDE: 1,                 // index step between tile kinds (top, wall, ...)
  VARIANTS: 1,                    // texture variants per axis (by world position)
  LEDGE: 16,                      // single, left, mid, right
  SOLID_MAX: 15,                  // up to here collide on every side; ledges are one-way
  OBJECTS: 'PHYmhSKTMVCBX',

  configure(ts) {
    if (!ts) return;
    this.TERRAIN = ts.terrain; this.KIND_STRIDE = ts.kindStride; this.VARIANTS = ts.variants;
    this.LEDGE = ts.ledge; this.SOLID_MAX = ts.solidMax;
  },

  parse(text) {
    const rows = text.replace(/\r/g, '').split('\n')
      .filter(l => l.length && l[0] !== '#');
    const h = rows.length;
    const w = Math.max(...rows.map(r => r.length));
    const at = (x, y) => (y < 0 || y >= h || x < 0 || x >= w) ? '.' : (rows[y][x] || '.');
    const solid = (ch) => this.TERRAIN[ch] !== undefined;

    const data = [];
    const objects = [];
    for (let y = 0; y < h; y++) {
      const row = [];
      for (let x = 0; x < w; x++) {
        const ch = at(x, y);
        if (solid(ch)) {
          const base = this.TERRAIN[ch];
          const top = !solid(at(x, y - 1));
          // Off the map counts as solid on the sides, so the level edges don't
          // get a wall drawn on them.
          const lEmpty = x > 0 && !solid(at(x - 1, y));
          const rEmpty = x < w - 1 && !solid(at(x + 1, y));
          let v;
          if (top) v = (lEmpty && rEmpty) ? 0 : lEmpty ? 1 : rEmpty ? 3 : 2;
          else v = lEmpty ? 4 : rEmpty ? 5 : (((x * 7 + y * 13) % 5) === 0 ? 7 : 6);
          const V = this.VARIANTS;
          row.push(base + v * this.KIND_STRIDE + (V > 1 ? (y % V) * V + (x % V) : 0));
        } else if (ch === '=') {
          const l = at(x - 1, y) === '=', r = at(x + 1, y) === '=';
          row.push(this.LEDGE + (!l && !r ? 0 : !l ? 1 : !r ? 3 : 2));
        } else {
          row.push(-1);
          if (this.OBJECTS.includes(ch)) {
            const o = { type: ch, tx: x, ty: y };
            // A moving platform's track: '-' to its right, or '|' above it.
            if (ch === 'M') { let n = 0; while (at(x + 1 + n, y) === '-') n++; o.travel = n; }
            if (ch === 'V') { let n = 0; while (at(x, y - 1 - n) === '|') n++; o.travel = n; }
            objects.push(o);
          }
        }
      }
      data.push(row);
    }
    return { w, h, data, objects };
  },

  /** World position for an object: standing things sit on the tile below;
   *  a moving platform is placed by its top-left corner. */
  place(o, T) {
    if (o.type === 'M' || o.type === 'V' || o.type === 'C') return { x: o.tx * T, y: o.ty * T };
    const standing = 'PHYSKTBX'.includes(o.type);
    return {
      x: o.tx * T + T / 2,
      y: standing ? (o.ty + 1) * T : o.ty * T + T / 2,
    };
  },
};
