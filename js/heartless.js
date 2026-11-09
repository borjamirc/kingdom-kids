/* ---------------------------------------------------------------------------
 * Shadow Heartless.
 *
 * Patrols, turns at walls and ledge edges, closes in when a kid is near, and
 * now and then melts into a puddle of shadow and slides along the ground the
 * way Shadows do in Kingdom Hearts. Up close it LUNGES -- after a short crouch
 * that tells you it's coming, so a kid can learn to swing or jump first.
 *
 * Still fair for a five-year-old: it only sinks when the kid is far away, a sunk
 * puddle rises again when a kid approaches, one hit or one stomp defeats it,
 * and while sunk it can neither hurt nor be hurt.
 *
 * Sheet layout (frame size, body, animation ranges) comes from
 * art/world/pride/sprites.json, so a generated sprite can replace the
 * procedural one without touching this file.
 * ------------------------------------------------------------------------- */
window.GAME = window.GAME || {};

GAME.Shadow = class Shadow {
  constructor(scene, x, y) {
    this.scene = scene;
    const m = this.meta = scene.spriteMeta.shadow;
    const s = scene.physics.add.sprite(x, y, 'shadow', 0).setOrigin(0.5, 1).setDepth(10);
    const [fw, fh] = m.frame, [bw, bh] = m.body;
    s.body.setSize(bw, bh).setOffset(Math.round((fw - bw) / 2), fh - bh);
    s.body.setMaxVelocityY(GAME.WORLD.maxFall);
    s.play('shadow-walk');
    scene.physics.add.collider(s, scene.layer);
    this.sprite = s;
    this.dir = Math.random() < 0.5 ? -1 : 1;
    this.state = 'walk';
    this.nextSink = scene.time.now + 2500 + Math.random() * 2500;
    this.nextLunge = scene.time.now + 1200;
    this.nearSince = 0;
  }

  get alive() { return this.state !== 'dead'; }
  /** Can be hit and can hurt. */
  get solid() { return this.state === 'walk' || this.state === 'windup' || this.state === 'lunge'; }
  /** Touching it costs a heart. */
  get harmful() { return this.solid; }

  bounds() {
    const b = this.sprite.body;
    return new Phaser.Geom.Rectangle(b.x, b.y, b.width, b.height);
  }

  update(time, player) {
    if (!this.alive) return;
    const s = this.sprite, b = s.body, C = GAME.SHADOW;
    if (s.y > this.scene.levelH + 40) { this.remove(); return; }

    const dx = player.x - s.x, dy = player.y - s.y;
    const near = Math.abs(dx) < 110 && Math.abs(dy) < 52;
    // How long this Shadow has been pestering the kid -- the friend steps in
    // only once it's clear the kid isn't managing on their own.
    if (Math.abs(dx) < 100 && Math.abs(dy) < 60) this.nearSince = this.nearSince || time;
    else this.nearSince = 0;

    if (this.state === 'walk') {
      if (near) this.dir = Math.sign(dx) || this.dir;
      else if (this.blockedAhead()) this.dir *= -1;
      b.setVelocityX(this.blockedAhead() && near ? 0 : this.dir * (near ? C.chase : C.walk));
      if (b.blocked.left) this.dir = 1;
      if (b.blocked.right) this.dir = -1;
      if (Math.abs(dx) < C.lungeRange && Math.abs(dy) < 30 && time > this.nextLunge && b.blocked.down) {
        this.windup(time);
      } else if (!near && Math.abs(dx) > 90 && time > this.nextSink && b.blocked.down) {
        this.sink();
      }
    } else if (this.state === 'windup') {
      b.setVelocityX(0);
      if (time > this.until) {
        this.state = 'lunge'; this.until = time + C.lungeMs;
        if (this.scene.anims.exists('shadow-lunge')) s.play('shadow-lunge');
        else s.play('shadow-walk');
      }
    } else if (this.state === 'lunge') {
      b.setVelocityX(this.blockedAhead() ? 0 : this.dir * C.lungeSpeed);
      if (time > this.until) {
        this.state = 'walk'; this.nextLunge = time + C.lungeEvery;
        s.play('shadow-walk');
      }
    } else if (this.state === 'sunk') {
      // A puddle that sees a kid coming rises up to fight, so encounters
      // actually happen instead of the kid strolling over a sunk Shadow.
      if (Math.abs(dx) < 120 && Math.abs(dy) < 60) { this.emerge(); return; }
      if (this.blockedAhead()) this.dir *= -1;
      b.setVelocityX(this.dir * 22);
    } else {
      b.setVelocityX(0);
    }
    s.setFlipX(this.dir < 0);
  }

  /** The tell: crouch and shiver before lunging. */
  windup(time) {
    const s = this.sprite, C = GAME.SHADOW;
    this.state = 'windup'; this.until = time + C.windupMs;
    s.anims.stop();
    if (this.meta.crouch !== undefined) {
      // A drawn crouch: hold it and shiver.
      s.setFrame(this.meta.crouch);
      this.scene.tweens.add({ targets: s, x: s.x + 1, duration: 40, yoyo: true, repeat: Math.floor(C.windupMs / 80) - 1 });
    } else {
      s.setFrame(this.meta.anims.walk[0]);
      this.scene.tweens.add({ targets: s, scaleY: 0.82, scaleX: 1.12, duration: C.windupMs / 2, yoyo: true });
    }
  }

  /** Wall in front, or no floor in front -- turn round instead of falling. */
  blockedAhead() {
    const s = this.sprite, b = s.body, T = GAME.WORLD.tile;
    const fx = s.x + this.dir * (b.width / 2 + 2);
    const floor = this.scene.layer.getTileAtWorldXY(fx, b.bottom + 2);
    const wall = this.scene.layer.getTileAtWorldXY(fx, b.bottom - T / 2);
    return !floor || (wall && wall.index <= GAME.Level.SOLID_MAX);
  }

  sink() {
    const s = this.sprite;
    this.state = 'sinking';
    s.anims.stop();
    this.scene.tweens.add({
      targets: s, scaleY: 0.2, duration: 220, ease: 'Quad.easeIn',
      onComplete: () => {
        if (!this.alive) return;
        this.state = 'sunk';
        // The puddle is a frame of the SAME sheet on the same canvas size --
        // swapping to a differently sized texture moved the physics body below
        // the feet and dropped Shadows out of the world.
        s.setFrame(this.meta.puddle).setScale(1, 1);
        this.scene.time.delayedCall(900 + Math.random() * 500, () => this.emerge());
      },
    });
  }

  emerge() {
    if (this.state !== 'sunk') return;     // proximity and the timer can both call this
    const s = this.sprite;
    this.state = 'emerging';
    s.setFrame(this.meta.anims.walk[0]).setScale(1, 0.2);
    this.scene.tweens.add({
      targets: s, scaleY: 1, duration: 240, ease: 'Back.easeOut',
      onComplete: () => {
        if (!this.alive) return;
        this.state = 'walk';
        s.play('shadow-walk');
        this.nextSink = this.scene.time.now + 3500 + Math.random() * 3000;
        this.nextLunge = Math.max(this.nextLunge, this.scene.time.now + 500);
      },
    });
  }

  /** Any hit defeats a Shadow. */
  hit() { this.defeat(); }

  /** Defeated -- by Keyblade, stomp or the Disney friend. */
  defeat() {
    if (!this.alive) return;
    const s = this.sprite, sc = this.scene;
    this.state = 'dead';
    sc.fx.hit(s.x, s.y - 12);
    sc.fx.heartRelease(s.x, s.y - 16);
    const drops = Math.random() < 0.25 ? 2 : Math.random() < 0.8 ? 1 : 0;
    for (let i = 0; i < drops; i++) sc.dropMunny(s.x + (i ? 8 : -6), s.y - 8);
    s.body.enable = false;
    s.anims.stop();
    sc.tweens.killTweensOf(s);
    sc.tweens.add({
      targets: s, alpha: 0, scaleX: 1.4, scaleY: 0.1, duration: 180,
      onComplete: () => s.destroy(),
    });
  }

  remove() {
    this.state = 'dead';
    this.sprite.destroy();
  }
};
