/* ---------------------------------------------------------------------------
 * The world's Disney friend -- Simba in the Pride Lands.
 *
 * He's a real physics body: gravity pulls him down, he stands on the ground,
 * ledges and moving platforms, and he walks and jumps to get around. To follow
 * the kid he heads for the places the kid actually STOOD ("footholds"), a
 * little way back along the kid's path -- never a point in the middle of one
 * of the kid's jumps, which is what left him floating in the air before.
 * When the next foothold is up a step, across a gap or on a ledge, he jumps to
 * it with an arc worked out to land on it.
 *
 * If he ever can't make it (stuck under a ledge, fell in a pit, left far
 * behind) he vanishes in a puff of sparkles and reappears just behind the kid,
 * so he can never be lost.
 *
 * Help a five-year-old doesn't have to manage:
 *   - he pounces on a Heartless or hyena that has been close to the kid for a
 *     while without being beaten -- he rescues a kid who's stuck, he doesn't
 *     play for them;
 *   - when the kid is down to one heart he roars and drops a heart.
 * ------------------------------------------------------------------------- */
window.GAME = window.GAME || {};

GAME.FRIEND = {
  follow: 64,          // stays this far back along the kid's path (px)
  speed: 178,          // a touch faster than the kid (165), so he catches up
  apex: 22,            // his jumps clear the spot they aim for by this much
  maxJumpVX: 260,
  reach: 150,          // looks this far ahead for the next foothold to go to
  stuckMs: 2200,       // no progress for this long -> puff, reappear
  maxDist: 380,        // further than this from the kid -> puff, reappear
};

GAME.Companion = class Companion {
  constructor(scene, x, y, key = 'simba') {
    this.scene = scene;
    this.key = key;
    this.cfg = GAME.FRIENDS[key] || GAME.FRIENDS.simba;
    const m = this.meta = scene.spriteMeta[key];
    const s = scene.physics.add.sprite(x, y, key, m.anims.walk[0]).setOrigin(0.5, 1).setDepth(12);
    const [fw, fh] = m.frame, [bw, bh] = m.body || [24, 18];
    s.body.setSize(bw, bh).setOffset(Math.round((fw - bw) / 2), fh - bh);
    s.body.setMaxVelocityY(GAME.WORLD.maxFall);
    scene.physics.add.collider(s, scene.layer);
    for (const mv of scene.movers || []) scene.physics.add.collider(s, mv.sprite);
    this.sprite = s;
    this.state = 'follow';
    this.nextPounce = scene.time.now + 3000;
    this.STUCK_MS = 1800;   // how long an enemy must pester the kid first (~one hit)
    this.nextHeart = 0;
    this.nextJump = 0;
    this.wantsUp = false;
    this.place(x, y);
  }

  // --- the world around him -------------------------------------------------
  solidAt(x, y) {
    const t = this.scene.layer.getTileAtWorldXY(x, y);
    if (t && t.index >= 0) return true;
    return this.scene.movers.some(m => {
      const b = m.sprite.body;
      return x >= b.left && x <= b.right && y >= b.top && y <= b.top + 10;
    });
  }

  wallAt(x, y) {
    const t = this.scene.layer.getTileAtWorldXY(x, y);
    return !!(t && t.index >= 0 && t.index <= GAME.Level.SOLID_MAX);
  }

  /** Something to walk onto ahead (a step down of up to ~2 tiles counts). */
  floorAhead(dir) {
    const b = this.sprite.body, x = this.sprite.x + dir * (b.halfWidth + 6);
    for (let dy = 2; dy <= 40; dy += 6) if (this.solidAt(x, b.bottom + dy)) return true;
    return false;
  }

  wallAhead(dir) {
    const b = this.sprite.body, x = this.sprite.x + dir * (b.halfWidth + 3);
    return this.wallAt(x, b.bottom - 6) || this.wallAt(x, b.bottom - 18);
  }

  /** Top of the wall just ahead, as a spot to jump onto -- or null when it's
   *  too tall to jump (a cliff: he'll catch up by puff instead). */
  ledgeAhead(dir) {
    const s = this.sprite, b = s.body, T = GAME.WORLD.tile;
    const x = s.x + dir * (b.halfWidth + 3);
    for (let k = 1; k <= 6; k++) {
      const y = b.bottom - k * T + 4;
      if (!this.wallAt(x, y)) {
        const top = Math.floor((y + T) / T) * T;          // top edge of the last wall tile
        return { x: s.x + dir * (b.halfWidth + 14), y: top };
      }
    }
    return null;
  }

  // --- the kid's footholds ----------------------------------------------------
  /** Where a foothold is now (one on a moving platform moves with it). */
  pos(f) {
    return f.mover ? { x: f.mover.sprite.x + f.ox, y: f.mover.sprite.y + f.oy } : f;
  }

  record(player) {
    const pb = player.body;
    if (this.scene.busy || !(pb.blocked.down || pb.touching.down)) return;
    const last = this.footholds[this.footholds.length - 1];
    const lp = last && this.pos(last);
    if (lp && Math.abs(player.x - lp.x) < 6 && Math.abs(player.y - lp.y) < 4) return;
    const mover = this.scene.movers.find(m => m.riding(pb));
    this.footholds.push(mover
      ? { mover, ox: player.x - mover.sprite.x, oy: player.y - mover.sprite.y }
      : { x: player.x, y: player.y });
    if (this.footholds.length > 260) this.footholds.shift();
  }

  /** Index of the foothold `follow` px of path behind the kid, or -1. */
  targetIndex(player) {
    let need = GAME.FRIEND.follow, px = player.x, py = player.y;
    for (let i = this.footholds.length - 1; i >= 0; i--) {
      const p = this.pos(this.footholds[i]);
      need -= Math.hypot(p.x - px, p.y - py);
      px = p.x; py = p.y;
      if (need <= 0) return i;
    }
    return -1;
  }

  /** The next foothold to go to: the furthest one along the kid's path, up to
   *  the target, that's within reach from where he stands. */
  waypoint(ti) {
    const s = this.sprite, F = GAME.FRIEND;
    let j = 0, best = Infinity;
    for (let i = 0; i <= ti; i++) {
      const p = this.pos(this.footholds[i]);
      const d = Math.hypot(p.x - s.x, p.y - s.y);
      if (d < best) { best = d; j = i; }
    }
    let k = Math.min(j + 1, ti);
    for (let i = j + 1; i <= ti; i++) {
      const p = this.pos(this.footholds[i]);
      if (Math.abs(p.x - s.x) < F.reach && Math.abs(p.y - s.y) < 110) k = i;
    }
    const p = this.pos(this.footholds[k]);
    if (j > 12) this.footholds.splice(0, j - 12);      // behind him for good
    return p;
  }

  // --- movement ------------------------------------------------------------------
  /** Jump on an arc that peaks a little above the target and comes down on it. */
  jump(t, time) {
    const b = this.sprite.body, F = GAME.FRIEND, g = this.scene.physics.world.gravity.y;
    const dx = t.x - this.sprite.x, down = t.y - this.sprite.y;     // down > 0: lower
    const h = Math.max(-down, 0) + F.apex;
    const vy = Math.sqrt(2 * g * h);
    const flight = vy / g + Math.sqrt((2 * Math.max(4, h + down)) / g);
    const vx = Phaser.Math.Clamp(dx / flight, -F.maxJumpVX, F.maxJumpVX);
    b.setVelocity(vx, -vy);
    this.airVX = vx;
    this.nextJump = time + 380;
  }

  /** Vanish and reappear on solid ground just behind the kid. */
  poof(player) {
    const pb = player.body;
    if (!(pb.blocked.down || pb.touching.down)) return false;     // wait for them to land
    let spot = null;
    for (let i = this.footholds.length - 1; i >= 0 && !spot; i--) {
      const p = this.pos(this.footholds[i]);
      if (Math.abs(p.x - player.x) >= 30 && Math.abs(p.x - player.x) < 90 && this.solidAt(p.x, p.y + 3)) spot = p;
    }
    if (!spot) spot = { x: player.x, y: player.y };
    this.scene.fx.sparkles(this.sprite.x, this.sprite.y - 14, 0xffd27c, 6);
    this.sprite.body.reset(spot.x, spot.y - 1);
    this.scene.fx.sparkles(spot.x, spot.y - 14, 0xffd27c, 8);
    this.lastMoveX = spot.x; this.lastMoveAt = this.scene.time.now;
    return true;
  }

  /** Put him beside the kid -- a new world, or the kid back at a save point. */
  place(x, y) {
    this.footholds = [{ x, y }];
    const bx = this.solidAt(x - 40, y + 3) ? x - 40 : x;
    this.sprite.body.reset(bx, y - 1);
    this.state = 'follow';
    this.lastMoveX = bx; this.lastMoveAt = this.scene.time.now;
  }

  reset(x, y) {
    this.place(x, y);
    this.scene.fx.sparkles(this.sprite.x, y - 14, 0xffd27c, 6);
  }

  update(time, delta, player, hearts) {
    const s = this.sprite, b = s.body, F = GAME.FRIEND, m = this.meta;
    this.record(player);
    if (this.state !== 'follow') return;
    const onG = b.blocked.down || b.touching.down;

    // Where to go: the next foothold on the way to his place behind the kid.
    // Nothing to do while the kid's path is still shorter than his distance.
    const far = Math.hypot(player.x - s.x, player.y - s.y);
    const ti = this.targetIndex(player);
    const t = ti >= 0 ? this.waypoint(ti) : far > F.follow + 24 ? this.pos(this.footholds[0]) : null;

    // Never lost: fell in a pit, far behind, or trying to get somewhere and
    // not managing for a while.
    const wants = t && (Math.abs(t.x - s.x) > 20 || t.y - s.y < -12);
    this.wantsUp = !!(t && t.y < s.y - 40);
    if (!wants || Math.abs(s.x - this.lastMoveX) > 12) { this.lastMoveX = s.x; this.lastMoveAt = time; }
    const stuck = wants && time - this.lastMoveAt > F.stuckMs;
    if ((s.y > this.scene.levelH + 30 || far > F.maxDist || stuck) && this.poof(player)) return;

    let vx = 0;
    if (t) {
      const dx = t.x - s.x, dy = t.y - s.y, dir = Math.sign(dx);
      if (onG) {
        const higher = dy < -10;
        const gap = Math.abs(dx) > 8 && !this.floorAhead(dir) && dy < 30;
        const wall = Math.abs(dx) > 8 && this.wallAhead(dir);
        if (wall && time > this.nextJump) {
          // Up onto the step first, whatever is beyond it.
          const top = this.ledgeAhead(dir);
          if (top) this.jump(top, time);
        } else if (time > this.nextJump && ((higher && Math.abs(dx) < F.reach + 40) || gap)) {
          this.jump(t, time);
        } else if (Math.abs(dx) > 4) {
          vx = Phaser.Math.Clamp(dx * 6, -F.speed, F.speed);
        }
      }
    }
    // On the ground he walks; in the air he keeps the speed he left with (a
    // wall he slides up against zeroes it, so it's re-applied every frame and
    // carries him on over the top).
    if (onG && b.velocity.y >= 0) { b.setVelocityX(vx); this.airVX = vx; }
    else if (!onG) b.setVelocityX(this.airVX || 0);

    // Looks
    if (!onG) {
      const air = m.air !== undefined ? m.air : m.pounce;
      s.anims.stop(); s.setFrame(air !== undefined ? air : m.anims.walk[0]);
      if (Math.abs(b.velocity.x) > 10) s.setFlipX(b.velocity.x < 0);
    } else if (Math.abs(vx) > 20) {
      s.play(this.key + '-walk', true); s.setFlipX(vx < 0);
    } else {
      s.anims.stop(); s.setFrame(m.anims.walk[0]);
      s.setFlipX(player.x < s.x);
    }

    if (onG) this.tryPounce(time, player);
    if (hearts === 1 && time > this.nextHeart) this.giveHeart(time, player);
  }

  tryPounce(time, player) {
    if (time < this.nextPounce) return;
    const s = this.sprite;
    let best = null, bestD = 170;
    for (const e of this.scene.enemies) {
      if (!e.solid || !e.nearSince || time - e.nearSince < this.STUCK_MS) continue;
      const d = Math.abs(e.sprite.x - s.x);
      if (d < bestD && Math.abs(e.sprite.y - s.y) < 70) { best = e; bestD = d; }
    }
    if (!best) return;
    this.nextPounce = time + 4000;
    if (this.cfg.help === 'throw') { this.throwAt(best); return; }
    this.state = 'pounce';
    const sx = s.x, sy = s.y;
    s.body.enable = false;                     // the leap is choreographed, not simulated
    s.anims.stop(); s.setFrame(this.meta.pounce); s.setFlipX(best.sprite.x < sx);
    this.scene.fx.say(sx, sy - 34, this.cfg.shout);
    const prog = { t: 0 };
    this.scene.tweens.add({
      targets: prog, t: 1, duration: 340, ease: 'Sine.easeInOut',
      onUpdate: () => {
        if (!best.alive) return;
        const ex = best.sprite.x, ey = best.sprite.y;
        s.x = sx + (ex - sx) * prog.t;
        s.y = sy + (ey - sy) * prog.t - Math.sin(prog.t * Math.PI) * 34;
      },
      onComplete: () => {
        best.defeat();
        s.body.enable = true;
        s.body.reset(s.x, s.y);
        this.lastMoveX = s.x; this.lastMoveAt = this.scene.time.now;
        this.scene.time.delayedCall(220, () => { this.state = 'follow'; });
      },
    });
  }

  /** Olaf's help: stop, wind up, lob a snowball in an arc at the enemy. */
  throwAt(best) {
    const s = this.sprite, sc = this.scene, m = this.meta;
    this.state = 'throw';
    s.body.setVelocityX(0);
    s.anims.stop(); s.setFrame(m.throw !== undefined ? m.throw : m.anims.walk[0]);
    s.setFlipX(best.sprite.x < s.x);
    sc.fx.say(s.x, s.y - 40, this.cfg.shout);
    const sx = s.x + (best.sprite.x < s.x ? -8 : 8), sy = s.y - 28;
    const ball = sc.add.image(sx, sy, 'snowball').setDepth(13);
    const prog = { t: 0 };
    sc.tweens.add({
      targets: prog, t: 1, duration: 420, delay: 120,
      onUpdate: () => {
        const ex = best.sprite.x, ey = best.sprite.y - 12;
        ball.x = sx + (ex - sx) * prog.t;
        ball.y = sy + (ey - sy) * prog.t - Math.sin(prog.t * Math.PI) * 30;
        ball.angle += 12;
      },
      onComplete: () => {
        sc.fx.sparkles(ball.x, ball.y, 0xffffff, 10);
        ball.destroy();
        if (best.alive) best.defeat();
        sc.time.delayedCall(260, () => { if (this.state === 'throw') this.state = 'follow'; });
      },
    });
  }

  giveHeart(time, player) {
    this.nextHeart = time + 20000;
    const s = this.sprite;
    this.scene.fx.say(s.x, s.y - 34, this.cfg.heart);
    this.scene.dropHeart(s.x, s.y - 20, player.x);
  }
};
