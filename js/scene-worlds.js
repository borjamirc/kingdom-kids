/* ---------------------------------------------------------------------------
 * World select: a card per world (a window onto its painted background), with
 * a golden Keyhole on the worlds this device has already sealed.
 *
 * Every world is open from the start -- a five-year-old (or a parent) can go
 * straight to the one they want. Sealing is remembered in localStorage.
 * ------------------------------------------------------------------------- */
window.GAME = window.GAME || {};

GAME.progress = {
  KEY: 'kingdom-kids-progress',
  load() {
    try { return JSON.parse(localStorage.getItem(this.KEY)) || { sealed: {} }; }
    catch (e) { return { sealed: {} }; }
  },
  seal(worldId) {
    const p = this.load();
    p.sealed = p.sealed || {};
    p.sealed[worldId] = true;
    try { localStorage.setItem(this.KEY, JSON.stringify(p)); } catch (e) { /* private mode */ }
  },
  sealed(worldId) { return !!(this.load().sealed || {})[worldId]; },
  /** Star Gems found in a world, by their order in the level (left to right). */
  gems(worldId) { return ((this.load().gems || {})[worldId]) || []; },
  addGem(worldId, i) {
    const p = this.load();
    p.gems = p.gems || {};
    const got = new Set(p.gems[worldId] || []);
    got.add(i);
    p.gems[worldId] = [...got].sort();
    try { localStorage.setItem(this.KEY, JSON.stringify(p)); } catch (e) { /* private mode */ }
  },
  /** Best share of a world's coins ever collected in one run, 0-100. */
  coins(worldId) { return ((this.load().coins || {})[worldId]) || 0; },
  addCoins(worldId, pct) {
    const p = this.load();
    p.coins = p.coins || {};
    if (pct <= (p.coins[worldId] || 0)) return;
    p.coins[worldId] = pct;
    try { localStorage.setItem(this.KEY, JSON.stringify(p)); } catch (e) { /* private mode */ }
  },
};

GAME.WorldScene = class WorldScene extends Phaser.Scene {
  constructor() { super('worlds'); }

  init(data) { this.charId = data.characterId; }

  create() {
    const W = GAME.WORLD.width, H = GAME.WORLD.height;
    const first = GAME.WORLDS[0];
    this.add.image(0, 0, first.id + '-far').setOrigin(0).setAlpha(0.35);
    this.add.rectangle(0, 0, W, H, 0x120a1e, 0.55).setOrigin(0);

    const title = GAME.text(this, W / 2, 22, 'CHOOSE A WORLD', 16, '#fff3d0');
    title.setOrigin(0.5, 0).setShadow(2, 2, '#3a1a3a', 0, false, true);

    const c = GAME.byId(this.charId) || GAME.CHARACTERS[0];
    this.add.image(28, H - 12, GAME.portraitKey(c)).setOrigin(0.5, 1).setScale(0.5);

    const n = GAME.WORLDS.length, gap = n > 2 ? 16 : 28;
    const cw = Math.min(232, Math.floor((W - 40 - (n - 1) * gap) / n)), chh = n > 2 ? 112 : 130;
    this.cw = cw; this.chh = chh;
    const x0 = Math.round(W / 2 - (n * cw + (n - 1) * gap) / 2);
    this.cards = GAME.WORLDS.map((w, i) => {
      const x = x0 + i * (cw + gap), y = n > 2 ? 72 : 78;
      // A 1:1 window onto the world's far background (no scaling, so the
      // pixels stay crisp): centred on the spot named by `thumb` (the
      // top-left of a 232x130 window), or the middle.
      const far = this.add.image(0, 0, w.id + '-far').setOrigin(0);
      const [tx, ty] = w.thumb
        ? [Math.round(w.thumb[0] + (232 - cw) / 2), Math.round(w.thumb[1] + (130 - chh) / 2)]
        : [Math.round((far.width - cw) / 2), 80];
      far.setCrop(tx, ty, cw, chh).setPosition(x - tx, y - ty);
      const frame = this.add.graphics();
      const name = GAME.text(this, x + cw / 2, y + chh + 10, w.name.toUpperCase(), 8, '#fff3d0').setOrigin(0.5, 0);
      if (n <= 2) GAME.text(this, x + 6, y + chh + 24, 'WORLD ' + (i + 1), 8, '#9a92b0').setOrigin(0, 0);
      // Star Gems found here: three slots, lit or dark.
      const got = GAME.progress.gems(w.id);
      for (let g = 0; g < 3; g++) {
        const star = this.add.image(x + cw - 50 + g * 20, y + chh + 28, 'gem').setOrigin(0.5);
        if (!got.includes(g)) star.setTint(0x2a2440).setAlpha(0.8);
      }
      // Best coin percentage, once there is one.
      const pct = GAME.progress.coins(w.id);
      if (pct > 0) {
        const cx = n <= 2 ? x + cw / 2 - 22 : x + 10;
        this.add.image(cx, y + chh + 28, 'munny').setOrigin(0.5);
        GAME.text(this, cx + 8, y + chh + 24, pct + '%', 8, pct >= 100 ? '#ffe27a' : '#fff3d0').setOrigin(0, 0);
      }
      if (GAME.progress.sealed(w.id)) {
        const k = this.add.image(x + cw - 18, y + 22, w.id + '-keyhole').setScale(0.5);
        this.tweens.add({ targets: k, y: k.y - 3, duration: 900, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' });
        GAME.text(this, x + 8, y + 8, 'SEALED!', 8, '#ffe27a').setStroke('#3a1a1a', 3);
      }
      const zone = this.add.zone(x + cw / 2, y + chh / 2 + 16, cw, chh + 40).setInteractive({ useHandCursor: true });
      zone.on('pointerover', () => this.select(i));
      zone.on('pointerdown', () => { this.select(i); this.go(); });
      return { w, x, y, frame, name };
    });

    const back = GAME.text(this, W - 10, H - 20, '< KIDS', 8, '#c9c2dc').setOrigin(1, 0)
      .setInteractive({ useHandCursor: true });
    back.on('pointerdown', () => this.scene.start('select'));

    this.index = 0;
    // Start on the first world not sealed yet.
    const next = GAME.WORLDS.findIndex(w => !GAME.progress.sealed(w.id));
    this.select(next >= 0 ? next : 0);
    const kb = this.input.keyboard;
    kb.on('keydown-LEFT', () => this.select((this.index - 1 + n) % n));
    kb.on('keydown-RIGHT', () => this.select((this.index + 1) % n));
    kb.on('keydown-SPACE', () => this.go());
    kb.on('keydown-ENTER', () => this.go());
    kb.on('keydown-ESC', () => this.scene.start('select'));
  }

  select(i) {
    this.index = i;
    this.cards.forEach((c, j) => {
      const on = i === j;
      c.frame.clear();
      c.frame.lineStyle(on ? 3 : 2, on ? 0xffd27c : 0x5a4a78, 1)
        .strokeRect(c.x - 2, c.y - 2, this.cw + 4, this.chh + 4);
      c.name.setColor(on ? '#ffffff' : '#9a92b0');
    });
  }

  go() {
    this.scene.start('play', { characterId: this.charId, worldId: GAME.WORLDS[this.index].id });
  }
};
