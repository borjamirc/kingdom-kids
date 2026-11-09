/* ---------------------------------------------------------------------------
 * Moving platforms.
 *
 * In the level text, 'M' is a platform that slides right over the '-' after
 * it and back; 'V' rises over the '|' above it and back down. Both ease in
 * and out at the ends (a sine), so a kid can see where it will stop and step
 * on while it's slow.
 *
 * Only the top is solid, like a ledge: you can jump up through it from below.
 * A kid standing on it moves with it, up, down and sideways.
 * ------------------------------------------------------------------------- */
window.GAME = window.GAME || {};

GAME.MOVER = {
  speed: 34,             // px/s average along the track
  minPeriodMs: 3200,     // there and back, for short tracks
};

GAME.Mover = class Mover {
  /** (x, y) = top-left of the platform at its start; (dx, dy) = travel. */
  constructor(scene, x, y, dx, dy) {
    this.scene = scene;
    const meta = scene.worldMeta.mover;
    const surface = meta ? meta.surface : 0;
    const s = scene.physics.add.image(x, y - surface, scene.world.id + '-mover').setOrigin(0, 0).setDepth(2);
    const b = s.body;
    b.setAllowGravity(false).setImmovable(true);
    b.moves = false;                       // positioned by update(), not by velocity
    b.setSize(s.width, 8).setOffset(0, surface);
    b.checkCollision.down = false; b.checkCollision.left = false; b.checkCollision.right = false;
    this.sprite = s;
    this.x0 = s.x; this.y0 = s.y; this.dx = dx; this.dy = dy;
    const dist = Math.hypot(dx, dy);
    this.period = Math.max(GAME.MOVER.minPeriodMs, (2 * dist / GAME.MOVER.speed) * 1000);
    this.phase = 0;
  }

  /** Where the platform should be at time t: 0 -> 1 -> 0 along the track. */
  at(t) {
    const k = (1 - Math.cos((2 * Math.PI * t) / this.period)) / 2;
    return { x: this.x0 + this.dx * k, y: this.y0 + this.dy * k };
  }

  /** riders: the sprites that can stand on it (the kid, the Disney friend). */
  update(time, delta, riders) {
    const s = this.sprite, p = this.at(time);
    const dx = p.x - s.x, dy = p.y - s.y;
    // Placed exactly on its track every frame (driving it with velocity
    // overshot whenever physics ran two steps in one frame), and whoever is
    // standing on it is carried by the same amount.
    const on = riders.filter(r => r.body && r.body.enable && this.riding(r.body));
    s.setPosition(p.x, p.y);
    s.body.updateFromGameObject();
    // Only the sprite: Arcade copies it into the body at the next step (syncing
    // the body here as well makes postUpdate apply the carry twice).
    for (const r of on) { r.x += dx; r.y += dy; }
  }

  riding(pb) {
    const b = this.sprite.body;
    return pb.velocity.y >= -1 && pb.right > b.left + 2 && pb.left < b.right - 2 &&
      Math.abs(pb.bottom - b.top) < 6;
  }
};

/* ---------------------------------------------------------------------------
 * Crumbling ice ('C' in the level text, 4 tiles wide, placed by its top-left
 * corner). Stand on it and it shivers for a moment, then cracks and drops;
 * a few seconds later it freezes back into place. Only the top is solid.
 * ------------------------------------------------------------------------- */
GAME.Crumble = class Crumble {
  constructor(scene, x, y) {
    this.scene = scene;
    const meta = scene.worldMeta.crumble || { surface: 0 };
    const s = scene.physics.add.image(x, y - meta.surface, scene.world.id + '-crumble').setOrigin(0, 0).setDepth(2);
    const b = s.body;
    b.setAllowGravity(false).setImmovable(true);
    b.moves = false;
    b.setSize(s.width, 8).setOffset(0, meta.surface);
    b.checkCollision.down = false; b.checkCollision.left = false; b.checkCollision.right = false;
    this.sprite = s;
    this.x0 = s.x; this.y0 = s.y;
    this.state = 'solid';
    this.until = 0;
  }

  riding(pb) { return GAME.Mover.prototype.riding.call(this, pb); }

  update(time, riders) {
    const s = this.sprite, C = GAME.CRUMBLE;
    if (this.state === 'solid') {
      if (riders.some(r => r.body && r.body.enable && this.riding(r.body))) {
        this.state = 'shaking'; this.until = time + C.shakeMs;
      }
    } else if (this.state === 'shaking') {
      s.x = this.x0 + (Math.floor(time / 45) % 2 ? 1 : -1);
      if (time > this.until) this.fall(time);
    } else if (this.state === 'gone' && time > this.until) {
      // Come back only when nobody is standing where it will appear.
      const home = new Phaser.Geom.Rectangle(this.x0, this.y0 - 8, s.width, s.height + 8);
      const blocked = riders.some(r => r.body && Phaser.Geom.Intersects.RectangleToRectangle(home,
        new Phaser.Geom.Rectangle(r.body.x, r.body.y, r.body.width, r.body.height)));
      if (!blocked) this.restore();
    }
  }

  fall(time) {
    const s = this.sprite, sc = this.scene;
    this.state = 'gone'; this.until = time + GAME.CRUMBLE.goneMs;
    s.x = this.x0;
    s.body.enable = false;
    sc.fx.sparkles(s.x + s.width / 2, s.y + 6, 0xdff4ff, 10);
    sc.tweens.add({ targets: s, y: this.y0 + 70, alpha: 0, duration: 450, ease: 'Quad.easeIn' });
  }

  restore() {
    const s = this.sprite;
    this.state = 'solid';
    this.scene.tweens.killTweensOf(s);
    s.setPosition(this.x0, this.y0).setAlpha(0);
    s.body.enable = true;
    s.body.updateFromGameObject();
    this.scene.tweens.add({ targets: s, alpha: 1, duration: 300 });
    this.scene.fx.sparkles(s.x + s.width / 2, s.y + 4, 0xdff4ff, 6);
  }
};
