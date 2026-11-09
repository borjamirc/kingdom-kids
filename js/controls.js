/* ---------------------------------------------------------------------------
 * Input: four on-screen buttons plus keyboard.
 *
 * Held state comes from BOTH sources, unioned:
 *   1. polling every active pointer against the button circles each frame, and
 *   2. explicit pointerdown/move/up bookkeeping.
 * Either alone has a failure mode. Polling misses a tap that goes down and up
 * between two frames -- which is exactly what a jump or an attack is, while a
 * direction is held for many frames and is never missed. Events alone lose a
 * finger that slides off a button or is swallowed by a browser gesture.
 *
 * Presses are additionally LATCHED on pointerdown, so a tap shorter than one
 * frame still fires. That is the difference between "jump doesn't work" and
 * "jump works".
 * ------------------------------------------------------------------------- */
window.GAME = window.GAME || {};

GAME.Controls = class Controls {
  constructor(scene) {
    this.scene = scene;
    const H = GAME.WORLD.height;

    // On a landscape phone the 360-tall screen is shown ~1.08x, so a radius of
    // 42 is ~91 physical px across. The hit radius is far larger than the
    // circle you can see -- small hands land wide.
    const W = GAME.WORLD.width;
    const R = 42, HIT = 64, y = H - 62;
    this.buttons = [
      { id: 'left',   x: 58,      y: y, r: R, hit: HIT, glyph: 'left' },
      { id: 'right',  x: 156,     y: y, r: R, hit: HIT, glyph: 'right' },
      { id: 'attack', x: W - 156, y: y, r: R, hit: HIT, glyph: 'blade' },
      { id: 'jump',   x: W - 58,  y: y, r: R, hit: HIT, glyph: 'up' },
    ];

    this.state = this.blank();
    this.prev = this.blank();
    this.latch = this.blank();     // set by pointerdown, consumed by update()
    this.consumed = this.blank();
    this.byPointer = {};           // pointerId -> button id

    // Phaser tracks one pointer by default; without these, holding right and
    // tapping jump would cancel the hold.
    scene.input.addPointer(3);

    scene.input.on('pointerdown', (p) => {
      const b = this.hitTest(p.x, p.y);
      if (b) { this.byPointer[p.id] = b.id; this.latch[b.id] = true; }
    });
    scene.input.on('pointermove', (p) => {
      if (!p.isDown) { delete this.byPointer[p.id]; return; }
      const b = this.hitTest(p.x, p.y);
      if (b) this.byPointer[p.id] = b.id; else delete this.byPointer[p.id];
    });
    const release = (p) => { delete this.byPointer[p.id]; };
    scene.input.on('pointerup', release);
    scene.input.on('pointerupoutside', release);
    scene.input.on('pointercancel', release);
    scene.input.on('gameout', () => { this.byPointer = {}; });

    const kb = scene.input.keyboard;
    this.keys = kb.addKeys({
      left: Phaser.Input.Keyboard.KeyCodes.LEFT,
      right: Phaser.Input.Keyboard.KeyCodes.RIGHT,
      up: Phaser.Input.Keyboard.KeyCodes.UP,
      space: Phaser.Input.Keyboard.KeyCodes.SPACE,
      z: Phaser.Input.Keyboard.KeyCodes.Z,
      x: Phaser.Input.Keyboard.KeyCodes.X,
      f: Phaser.Input.Keyboard.KeyCodes.F,
    });
    kb.addCapture([
      Phaser.Input.Keyboard.KeyCodes.LEFT, Phaser.Input.Keyboard.KeyCodes.RIGHT,
      Phaser.Input.Keyboard.KeyCodes.UP, Phaser.Input.Keyboard.KeyCodes.DOWN,
      Phaser.Input.Keyboard.KeyCodes.SPACE,
    ]);

    this.gfx = scene.add.graphics().setScrollFactor(0).setDepth(1000);
    const blade = this.buttons.find(b => b.glyph === 'blade');
    if (scene.textures.exists('keyblade')) {
      this.bladeIcon = scene.add.image(blade.x, blade.y, 'keyblade')
        .setScale(2).setAngle(-35).setScrollFactor(0).setDepth(1001).setAlpha(0.8);
    }
    this.draw();
  }

  blank() { return { left: false, right: false, jump: false, attack: false }; }

  /** Nearest containing button, so overlapping hit zones can't fire two
   *  directions at once. */
  hitTest(px, py) {
    let best = null, bestD = Infinity;
    for (const b of this.buttons) {
      const d = Phaser.Math.Distance.Squared(px, py, b.x, b.y);
      if (d <= b.hit * b.hit && d < bestD) { bestD = d; best = b; }
    }
    return best;
  }

  update() {
    this.prev = this.state;
    this.consumed = this.latch;
    this.latch = this.blank();

    const s = this.blank();

    // (1) polled pointers
    for (const p of this.scene.input.manager.pointers) {
      if (!p || !p.isDown) continue;
      const b = this.hitTest(p.x, p.y);
      if (b) s[b.id] = true;
    }
    // (2) event bookkeeping
    for (const id in this.byPointer) s[this.byPointer[id]] = true;
    // (3) a press latched since the last frame counts as held this frame too,
    //     so a sub-frame tap still reads as a real button press.
    for (const n in this.consumed) if (this.consumed[n]) s[n] = true;

    const k = this.keys;
    if (k.left.isDown) s.left = true;
    if (k.right.isDown) s.right = true;
    if (k.space.isDown || k.up.isDown) s.jump = true;
    if (k.z.isDown || k.x.isDown || k.f.isDown) s.attack = true;

    const changed = ['left', 'right', 'jump', 'attack'].some(n => s[n] !== this.state[n]);
    this.state = s;
    if (changed) this.draw();
  }

  pressed(name) {
    return (this.state[name] && !this.prev[name]) || this.consumed[name];
  }
  held(name) { return this.state[name]; }

  draw() {
    const g = this.gfx;
    g.clear();
    for (const b of this.buttons) {
      const on = this.state[b.id];
      g.fillStyle(0xffffff, on ? 0.30 : 0.12);
      g.fillCircle(b.x, b.y, b.r);
      g.lineStyle(2, 0xffffff, on ? 0.85 : 0.42);
      g.strokeCircle(b.x, b.y, b.r);
      g.fillStyle(0xffffff, on ? 0.98 : 0.72);
      this.glyph(g, b);
    }
  }

  glyph(g, b) {
    const s = b.r * 0.42;
    switch (b.glyph) {
      case 'left':
        g.fillTriangle(b.x + s * 0.55, b.y - s, b.x + s * 0.55, b.y + s, b.x - s * 0.75, b.y);
        break;
      case 'right':
        g.fillTriangle(b.x - s * 0.55, b.y - s, b.x - s * 0.55, b.y + s, b.x + s * 0.75, b.y);
        break;
      case 'up':
        g.fillTriangle(b.x - s, b.y + s * 0.55, b.x + s, b.y + s * 0.55, b.x, b.y - s * 0.75);
        break;
      case 'blade':
        if (this.bladeIcon) this.bladeIcon.setAlpha(this.state.attack ? 1 : 0.8);
        else g.fillCircle(b.x, b.y, s * 0.85);
        break;
    }
  }
};
