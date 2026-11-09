/* ---------------------------------------------------------------------------
 * Character select. Builds itself by iterating GAME.CHARACTERS.
 *
 * Portraits are drawn 1:1 -- tools/pixelize.py already sized them to the cast's
 * true relative standing heights, so Baltazar reads as a baby next to Sara
 * without any scaling here (scaling would break the pixel grid).
 * ------------------------------------------------------------------------- */
window.GAME = window.GAME || {};

GAME.SelectScene = class SelectScene extends Phaser.Scene {
  constructor() { super('select'); }

  create() {
    const W = GAME.WORLD.width, H = GAME.WORLD.height;
    const world = GAME.WORLDS[0];

    this.far = this.add.image(0, 0, world.id + '-far').setOrigin(0);
    this.mid = this.add.tileSprite(0, 0, W, H, world.id + '-mid').setOrigin(0);
    this.floorBand = this.add.rectangle(0, 252, W, H - 252, 0x1b1028, 0.6).setOrigin(0);

    const title = GAME.text(this, W / 2, 22, 'CHOOSE YOUR KID', 16, '#fff3d0');
    title.setOrigin(0.5, 0).setShadow(2, 2, '#3a1a3a', 0, false, true);
    GAME.text(this, W / 2, 46, 'THEN PICK A WORLD', 8, '#ffd27c').setOrigin(0.5, 0);

    const n = GAME.CHARACTERS.length;
    const slotW = Math.floor(W / n);
    const baseline = 252;

    this.slots = [];
    GAME.CHARACTERS.forEach((c, i) => {
      const cx = Math.round(slotW * (i + 0.5));
      const frame = this.add.graphics();
      const img = this.add.image(cx, baseline, GAME.portraitKey(c)).setOrigin(0.5, 1);
      const label = GAME.text(this, cx, baseline + 12, c.name.toUpperCase(), 8, '#c9c2dc').setOrigin(0.5, 0);
      const zone = this.add.zone(cx, 170, slotW - 4, 230).setInteractive({ useHandCursor: true });
      zone.on('pointerover', () => this.select(i));
      zone.on('pointerdown', () => { this.select(i); this.confirm(); });
      this.slots.push({ c, img, label, frame, cx });
    });

    const hint = GAME.text(this, W / 2, H - 28, 'TAP A KID TO PLAY', 8, '#fff3d0').setOrigin(0.5, 0);
    this.tweens.add({ targets: hint, alpha: 0.35, duration: 700, yoyo: true, repeat: -1 });

    this.index = 0;
    this.select(0);
    const kb = this.input.keyboard;
    kb.on('keydown-LEFT', () => this.select((this.index - 1 + n) % n));
    kb.on('keydown-RIGHT', () => this.select((this.index + 1) % n));
    kb.on('keydown-SPACE', () => this.confirm());
    kb.on('keydown-ENTER', () => this.confirm());
  }

  update(t) {
    // The panorama drifts slowly back and forth; the hills scroll past.
    const span = this.far.width - GAME.WORLD.width;
    this.far.x = -Math.round(span * (0.5 - 0.5 * Math.cos(t * 0.00006)));
    this.mid.tilePositionX = Math.round(t * 0.012);
  }

  select(i) {
    this.index = i;
    const slotW = Math.floor(GAME.WORLD.width / this.slots.length);
    this.slots.forEach((s, j) => {
      const on = i === j;
      s.frame.clear();
      if (on) {
        s.frame.fillStyle(0xffd27c, 0.16).fillRect(s.cx - slotW / 2 + 3, 70, slotW - 6, 198);
        s.frame.lineStyle(2, 0xffd27c, 0.9).strokeRect(s.cx - slotW / 2 + 3, 70, slotW - 6, 198);
      }
      s.label.setColor(on ? '#ffffff' : '#9a92b0');
      s.img.setAlpha(on ? 1 : 0.7);
    });
  }

  confirm() {
    this.scene.start('worlds', { characterId: this.slots[this.index].c.id });
  }
};
