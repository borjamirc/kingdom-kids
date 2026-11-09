/* ---------------------------------------------------------------------------
 * Charging enemy: the Pride Lands' hyena, Arendelle's wolf (same behaviour,
 * different sheet and voice -- see GAME.CHARGERS).
 *
 * Patrols; when it spots a kid on its level it crouches (a clear, readable
 * tell), then CHARGES in a straight line until it hits a wall or the edge of
 * its ground, then stops to pant. Takes two hits -- Keyblade, stomp or Simba.
 * A beaten hyena doesn't die: it yelps and runs off the screen, which is a
 * kinder ending for a five-year-old than a defeat animation.
 * ------------------------------------------------------------------------- */
window.GAME = window.GAME || {};

GAME.Hyena = class Hyena {
  constructor(scene, x, y, key = 'hyena') {
    this.scene = scene;
    this.key = key;
    this.voice = GAME.CHARGERS[key] || GAME.CHARGERS.hyena;
    const m = this.meta = scene.spriteMeta[key];
    const s = scene.physics.add.sprite(x, y, key, 0).setOrigin(0.5, 1).setDepth(10);
    const [fw, fh] = m.frame, [bw, bh] = m.body;
    s.body.setSize(bw, bh).setOffset(Math.round((fw - bw) / 2), fh - bh);
    s.body.setMaxVelocityY(GAME.WORLD.maxFall);
    scene.physics.add.collider(s, scene.layer);
    s.play(this.key + '-walk');
    this.sprite = s;
    this.hp = GAME.HYENA.hp;
    this.dir = Math.random() < 0.5 ? -1 : 1;
    this.state = 'patrol';
    this.until = 0;
    this.nextCharge = scene.time.now + 1500;
    this.nearSince = 0;
  }

  get alive() { return this.state !== 'dead'; }
  /** Can be hit. */
  get solid() { return this.alive; }
  /** Touching it costs a heart -- not while it's dizzy from a hit. */
  get harmful() { return this.alive && this.state !== 'dizzy'; }

  /** A still pose: a named frame from sprites.json, or the first walk frame. */
  pose(name) {
    const m = this.meta;
    this.sprite.anims.stop();
    this.sprite.setFrame(m[name] !== undefined ? m[name] : m.anims.walk[0]);
  }

  bounds() {
    const b = this.sprite.body;
    return new Phaser.Geom.Rectangle(b.x, b.y, b.width, b.height);
  }

  blockedAhead() {
    const s = this.sprite, b = s.body, T = GAME.WORLD.tile;
    const fx = s.x + this.dir * (b.width / 2 + 2);
    const floor = this.scene.layer.getTileAtWorldXY(fx, b.bottom + 2);
    const wall = this.scene.layer.getTileAtWorldXY(fx, b.bottom - T / 2);
    return !floor || (wall && wall.index <= GAME.Level.SOLID_MAX);
  }

  update(time, player) {
    if (!this.alive) return;
    const s = this.sprite, b = s.body, C = GAME.HYENA;
    if (s.y > this.scene.levelH + 40) { this.state = 'dead'; s.destroy(); return; }
    const dx = player.x - s.x, dy = player.y - s.y;
    if (Math.abs(dx) < 100 && Math.abs(dy) < 60) this.nearSince = this.nearSince || time;
    else this.nearSince = 0;

    switch (this.state) {
      case 'patrol':
        if (this.blockedAhead() || b.blocked.left || b.blocked.right) this.dir *= -1;
        b.setVelocityX(this.dir * C.walk);
        s.anims.timeScale = 0.6;
        if (time > this.nextCharge && Math.abs(dx) < C.sight && Math.abs(dy) < 40 && b.blocked.down) {
          this.dir = Math.sign(dx) || this.dir;
          this.state = 'windup'; this.until = time + C.windupMs;
          this.pose('crouch');
          this.scene.tweens.add({ targets: s, scaleY: 0.85, duration: 120, yoyo: true, repeat: 1 });
        }
        break;
      case 'windup':
        b.setVelocityX(0);
        s.setTint(Math.floor(time / 80) % 2 ? 0xffd0a0 : 0xffffff);
        if (time > this.until) {
          s.clearTint();
          this.state = 'charge'; this.until = time + C.chargeMs;
          s.play(this.key + '-walk'); s.anims.timeScale = 1.6;
          this.scene.fx.say(s.x, s.y - 30, this.voice.growl);
        }
        break;
      case 'charge':
        b.setVelocityX(this.dir * C.charge);
        if (time > this.until || this.blockedAhead() || b.blocked.left || b.blocked.right) {
          this.state = 'rest'; this.until = time + C.restMs;
          this.pose('rest');
        }
        break;
      case 'rest':
        b.setVelocityX(0);
        if (time > this.until) {
          this.state = 'patrol'; this.nextCharge = time + C.cooldownMs;
          s.play(this.key + '-walk');
        }
        break;
      case 'dizzy':
        b.setVelocityX(b.velocity.x * 0.9);
        if (time > this.nextStar) {
          this.nextStar = time + 260;
          this.scene.fx.sparkles(s.x + Math.sin(time / 90) * 8, s.y - this.meta.frame[1] + 2, 0xffe27a, 1);
        }
        if (time > this.until) {
          this.state = 'patrol'; s.clearTint(); s.setAngle(0);
          this.scene.tweens.killTweensOf(s);
          s.play(this.key + '-walk');
          this.nextCharge = time + GAME.HYENA.cooldownMs;
        }
        break;
    }
    s.setFlipX(this.dir < 0);
  }

  /** One point of damage, from any source. */
  hit(fromDir) {
    if (!this.alive) return;
    const s = this.sprite, sc = this.scene;
    this.hp--;
    sc.fx.hit(s.x, s.y - 14);
    if (this.hp <= 0) { this.defeat(); return; }
    // Knocked a little way back, then dizzy: stars, a wobble, no biting.
    this.state = 'dizzy'; this.until = sc.time.now + GAME.HYENA.dizzyMs; this.nextStar = 0;
    this.pose('rest');
    s.setTintFill(0xffffff);
    sc.time.delayedCall(90, () => { if (this.alive) s.setTint(0xffd0d0); });
    s.body.setVelocity((fromDir || -this.dir) * 90, -120);
    sc.tweens.add({ targets: s, angle: { from: -6, to: 6 }, duration: 260, yoyo: true, repeat: -1 });
    sc.fx.say(s.x, s.y - 30, '@_@');
  }

  defeat() {
    if (!this.alive) return;
    const s = this.sprite, sc = this.scene;
    this.state = 'dead';
    sc.fx.say(s.x, s.y - 30, this.voice.beaten);
    sc.dropReward(s.x, s.y - 8);
    s.body.enable = false;
    s.clearTint(); sc.tweens.killTweensOf(s); s.setAngle(0);
    // Runs away, embarrassed, instead of dying.
    const away = s.x < sc.player.x ? -1 : 1;
    s.setFlipX(away < 0); s.play(this.key + '-walk'); s.anims.timeScale = 2;
    sc.tweens.add({ targets: s, x: s.x + away * 260, duration: 900, ease: 'Quad.easeIn' });
    sc.tweens.add({ targets: s, alpha: 0, delay: 500, duration: 400, onComplete: () => s.destroy() });
  }
};
