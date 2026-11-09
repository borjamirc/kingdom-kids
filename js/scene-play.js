/* ---------------------------------------------------------------------------
 * A world: scrolling level, one kid, the world's Disney friend, Heartless,
 * save points, and the Keyhole at the end.
 *
 * Can't-lose rules for a five-year-old: a hit costs a heart; running out, or
 * falling in a pit, puts you back at the last save point with full hearts. No
 * lives, no game over.
 * ------------------------------------------------------------------------- */
window.GAME = window.GAME || {};

GAME.PlayScene = class PlayScene extends Phaser.Scene {
  constructor() { super('play'); }

  init(data) {
    this.char = GAME.byId(data.characterId) || GAME.CHARACTERS[0];
    this.world = GAME.WORLDS.find(w => w.id === data.worldId) || GAME.WORLDS[0];
  }

  create() {
    const c = this.char, w = this.world, T = GAME.WORLD.tile;
    const W = GAME.WORLD.width, H = GAME.WORLD.height;
    this.fx = new GAME.Fx(this);
    this.spriteMeta = GAME.SPRITES;
    this.registerAnims();
    this.makeSnowball();

    // --- level --------------------------------------------------------------
    this.worldMeta = this.cache.json.get(w.id + '-meta') || {};
    GAME.Level.configure(this.worldMeta.tileset);
    const lvl = GAME.Level.parse(this.cache.text.get(w.id + '-level'));
    this.levelW = lvl.w * T; this.levelH = lvl.h * T;

    // Far: one painted panorama, a little wider than the screen, slid across
    // once over the whole level. Mid: hills that tile, at about a third of the
    // camera's speed.
    this.bgFar = this.add.image(0, 0, w.id + '-far').setOrigin(0).setScrollFactor(0).setDepth(-90);
    this.bgMid = this.add.tileSprite(0, 0, W, H, w.id + '-mid').setOrigin(0).setScrollFactor(0).setDepth(-80);

    const map = this.make.tilemap({ data: lvl.data, tileWidth: T, tileHeight: T });
    const tiles = map.addTilesetImage(w.id + '-tiles', w.id + '-tiles', T, T, 0, 0);
    this.layer = map.createLayer(0, tiles, 0, 0).setDepth(0);
    this.layer.setCollisionBetween(0, GAME.Level.SOLID_MAX);
    // Ledges are one-way: only the top face is solid, so you jump up through them.
    this.layer.forEachTile(t => {
      if (t.index >= GAME.Level.LEDGE) t.setCollision(false, false, true, false);
    });

    this.decorateTerrain(lvl);

    this.physics.world.setBounds(0, 0, this.levelW, this.levelH + 300);
    this.physics.world.setBoundsCollision(true, true, false, false);

    // --- objects ------------------------------------------------------------
    // Phaser reuses this scene object on every run, so anything a previous run
    // left set (a finished sealing, the old Keyhole) must be cleared here.
    this.enemies = []; this.pickups = []; this.saves = []; this.movers = [];
    this.crumbles = []; this.bounces = [];
    const trees = (this.worldMeta.trees || [0]).length;
    // Tile index ranges that are slippery ice (a frozen lake).
    this.slippery = (this.worldMeta.tileset && this.worldMeta.tileset.slippery) || [];
    this.keyhole = null; this.sealing = false;
    let spawn = { x: 3 * T, y: 20 * T };
    for (const o of lvl.objects) {
      const p = GAME.Level.place(o, T);
      if (o.type === 'P') spawn = p;
      else if (o.type === 'T') {
        this.add.image(p.x, p.y + 4, w.id + '-tree-' + ((o.tx * 7) % trees)).setOrigin(0.5, 1).setDepth(-5);
      }
      else if (o.type === 'M') this.movers.push(new GAME.Mover(this, p.x, p.y, o.travel * T, 0));
      else if (o.type === 'V') this.movers.push(new GAME.Mover(this, p.x, p.y, 0, -o.travel * T));
      else if (o.type === 'H') this.enemies.push(new GAME.Shadow(this, p.x, p.y));
      else if (o.type === 'Y') this.enemies.push(new GAME.Hyena(this, p.x, p.y, w.charger || 'hyena'));
      else if (o.type === 'C') this.crumbles.push(new GAME.Crumble(this, p.x, p.y));
      else if (o.type === 'B') this.addBounce(p.x, p.y);
      else if (o.type === 'm') this.addPickup('munny', p.x, p.y);
      else if (o.type === 'h') this.addPickup('heart', p.x, p.y);
      else if (o.type === 'S') this.addSave(p.x, p.y);
      else if (o.type === 'K') this.addKeyhole(p.x, p.y);
    }
    this.respawn = { x: spawn.x, y: spawn.y };

    // --- the kid ------------------------------------------------------------
    const [cw, ch] = c.cell, [ax, ay] = c.anchor;
    const pl = this.physics.add.sprite(spawn.x, spawn.y - 1, GAME.sheetKey(c, 'idle'), 0);
    pl.setOrigin(ax / cw, ay / ch).setDepth(15);
    const bw = Phaser.Math.Clamp(Math.round(c.figure[0] * 0.42), 10, 22);
    const bh = Math.round(c.figure[1] * 0.86);
    pl.body.setSize(bw, bh, false);
    // Body bottom = the bottom edge of the feet row, so standing puts the feet
    // exactly on the tile top.
    pl.body.setOffset(ax - Math.floor(bw / 2), ay + 1 - bh);
    pl.body.setMaxVelocityY(GAME.WORLD.maxFall);
    pl.setCollideWorldBounds(true);
    this.physics.add.collider(pl, this.layer);
    for (const m of this.movers) this.physics.add.collider(pl, m.sprite);
    for (const k of this.crumbles) this.physics.add.collider(pl, k.sprite);
    this.player = pl;

    this.blade = this.add.image(0, 0, 'keyblade').setOrigin(5.5 / 30, 5.5 / 14).setDepth(16).setVisible(false);
    this.swoosh = this.add.image(0, 0, 'swoosh').setDepth(17).setVisible(false).setTint(c.tint);

    this.facing = 1;
    this.hearts = GAME.COMBAT.hearts;
    this.munny = 0;
    this.swing = null;
    this.lastGround = 0; this.lastJumpPress = -9999;
    this.jumpCut = false; this.wasOnGround = true; this.landTimer = 0;
    this.invulnUntil = 0; this.knockUntil = 0;
    this.busy = false;                  // fainting, respawning or sealing

    this.friend = new GAME.Companion(this, spawn.x, spawn.y - 1, w.friend);
    for (const k of this.crumbles) this.physics.add.collider(this.friend.sprite, k.sprite);
    this.riders = [pl, this.friend.sprite];

    // --- camera -------------------------------------------------------------
    const cam = this.cameras.main;
    cam.setBounds(0, 0, this.levelW, this.levelH).setRoundPixels(true);
    cam.startFollow(pl, true, 0.12, 0.12);
    cam.setDeadzone(48, 40);
    cam.fadeIn(350, 0, 0, 0);

    // --- input + hud ----------------------------------------------------------
    this.controls = new GAME.Controls(this);
    this.buildHud();
    this.input.keyboard.on('keydown-ESC', () => this.scene.start('worlds', { characterId: this.char.id }));
  }

  /** Floating platforms drawn from their art pieces over the (hidden)
   *  one-way ledge tiles, and the grass tips along every dirt top. */
  decorateTerrain(lvl) {
    const T = GAME.WORLD.tile, id = this.world.id, L = GAME.Level, meta = this.worldMeta;
    const idx = (x, y) => (y < 0 || y >= lvl.h || x < 0 || x >= lvl.w) ? -1 : lvl.data[y][x];
    const pm = meta.platform;
    if (pm && this.textures.exists(id + '-platform')) {
      this.layer.forEachTile(t => { if (t.index >= L.LEDGE) t.setAlpha(0); });
      const F = pm.frames, isLedge = (x, y) => idx(x, y) >= L.LEDGE;
      for (let y = 0; y < lvl.h; y++) {
        for (let x = 0; x < lvl.w; x++) {
          if (!isLedge(x, y)) continue;
          const l = isLedge(x - 1, y), r = isLedge(x + 1, y);
          const f = !l && !r ? F.single : !l ? F.left : !r ? F.right : F.mid + (x % pm.mids);
          this.add.image(x * T, y * T - pm.surface, id + '-platform', f).setOrigin(0, 0).setDepth(1);
        }
      }
    }
    const fr = meta.tileset && meta.tileset.fringe;
    if (fr && this.textures.exists(id + '-fringe')) {
      const G = L.TERRAIN.G, top = (x, y) => { const i = idx(x, y); return i >= G && i < G + 4 * L.KIND_STRIDE; };
      for (let y = 0; y < lvl.h; y++) {
        for (let x = 0; x < lvl.w;) {
          if (!top(x, y)) { x++; continue; }
          let x1 = x;
          while (top(x1, y)) x1++;
          const ts = this.add.tileSprite(x * T, y * T - fr, (x1 - x) * T, fr, id + '-fringe').setOrigin(0, 0).setDepth(1);
          ts.tilePositionX = x * T;
          x = x1;
        }
      }
    }
  }

  registerAnims() {
    const A = this.anims;
    for (const c of GAME.CHARACTERS) {
      for (const name of ['idle', 'run']) {
        const key = GAME.animKey(c, name);
        if (!A.exists(key)) A.create({
          key, frameRate: c.anims[name].fps, repeat: -1,
          frames: A.generateFrameNumbers(GAME.sheetKey(c, name), { start: 0, end: c.frames[name] - 1 }),
        });
      }
    }
    // Enemy and friend animations come from sprites.json: '<sheet>-<anim>'.
    for (const [key, meta] of Object.entries(this.spriteMeta)) {
      for (const [name, [start, end]] of Object.entries(meta.anims || {})) {
        const k = key + '-' + name;
        if (A.exists(k)) continue;
        A.create({ key: k, frameRate: (meta.fps && meta.fps[name]) || 8,
          repeat: name === 'lunge' ? 0 : -1,
          frames: A.generateFrameNumbers(key, { start, end }) });
      }
    }
  }

  // ===========================================================================
  update(time, delta) {
    const c = this.char, p = this.player, b = p.body, ctl = this.controls, M = GAME.MOVE;
    ctl.update();
    this.updateParallax();
    for (const m of this.movers) m.update(time, delta, this.riders);
    for (const k of this.crumbles) k.update(time, this.riders);
    this.checkBounces();

    const onGround = b.blocked.down || b.touching.down;
    if (onGround) this.lastGround = time;
    if (onGround && !this.wasOnGround) this.landTimer = GAME.LAND_MS;
    this.wasOnGround = onGround;
    if (this.landTimer > 0) this.landTimer -= delta;

    if (!this.busy) {
      if (ctl.pressed('jump')) this.lastJumpPress = time;
      const knocked = time < this.knockUntil;

      // On slippery ice speed only creeps toward what the stick asks for, so
      // the kid slides into a run and glides to a stop.
      const ice = onGround && this.onIce();
      const run = (vx) => b.setVelocityX(ice ? b.velocity.x + (vx - b.velocity.x) * GAME.ICE.grip : vx);
      if (this.swing && onGround) run(0);                     // rooted on the ground
      else if (!this.swing && !knocked) {
        const l = ctl.held('left'), r = ctl.held('right');
        if (l && !r) { run(-M.speed); this.facing = -1; }
        else if (r && !l) { run(M.speed); this.facing = 1; }
        else run(0);
      }

      // Jump: coyote time + buffer, so slightly early or late presses still count.
      if (!this.swing && !knocked && time - this.lastJumpPress < M.bufferMs &&
          time - this.lastGround < M.coyoteMs) {
        b.setVelocityY(-M.jump);
        this.lastJumpPress = -9999; this.lastGround = -9999;
        this.jumpCut = true; this.landTimer = 0;
      }
      if (this.jumpCut && !ctl.held('jump') && b.velocity.y < 0) {
        b.setVelocityY(b.velocity.y * M.jumpCut);
        this.jumpCut = false;
      }
      if (b.velocity.y >= 0) this.jumpCut = false;

      if (ctl.pressed('attack') && !this.swing) this.startSwing(time);
    } else {
      b.setVelocityX(0);
    }

    p.setFlipX(this.facing < 0);
    this.updateSwing(time);
    this.updateAnim(onGround);

    // Frozen during the sealing, so nothing walks into the kid at the climax.
    if (!this.sealing) for (const e of this.enemies) e.update(time, p);
    else for (const e of this.enemies) if (e.alive && e.sprite.body) e.sprite.body.setVelocityX(0);
    if (!this.busy) {
      this.checkEnemyContact(time);
      this.checkPickups();
      this.checkSaves(time);
      this.checkKeyhole();
      if (p.y > this.levelH + 24) this.fellInPit();
    }
    this.friend.update(time, delta, p, this.hearts);
    if (time < this.invulnUntil) p.setAlpha(Math.floor(time / 70) % 2 ? 0.35 : 1);
    else p.setAlpha(1);
  }

  /** Is the kid standing on slippery ice? */
  onIce() {
    if (!this.slippery.length) return false;
    const b = this.player.body;
    for (const x of [b.left + 2, b.center.x, b.right - 2]) {
      const t = this.layer.getTileAtWorldXY(x, b.bottom + 2);
      if (t && this.slippery.some(([a, z]) => t.index >= a && t.index <= z)) return true;
    }
    return false;
  }

  /** A snow bounce pad: lands you (or the friend) and flings you up high. */
  addBounce(x, y) {
    const img = this.add.image(x, y + 3, this.world.id + '-bounce').setOrigin(0.5, 1).setDepth(4);
    this.bounces.push({ x, y: y + 3, img, w: img.width, h: img.height });
  }

  checkBounces() {
    for (const pad of this.bounces) {
      for (const r of this.riders) {
        const b = r.body;
        if (!b || !b.enable || b.velocity.y < 0) continue;
        // The friend only takes a pad when he's trying to get up somewhere --
        // not when his resting spot happens to be on top of it.
        if (r === this.friend.sprite && !this.friend.wantsUp) continue;
        if (b.right < pad.x - pad.w / 2 + 6 || b.left > pad.x + pad.w / 2 - 6) continue;
        if (b.bottom < pad.y - pad.h + 2 || b.bottom > pad.y + 3) continue;
        b.setVelocityY(-GAME.BOUNCE);
        if (r === this.player) { this.jumpCut = false; this.lastGround = -9999; this.landTimer = 0; }
        this.tweens.killTweensOf(pad.img);
        pad.img.setScale(1.15, 0.6);
        this.tweens.add({ targets: pad.img, scaleX: 1, scaleY: 1, duration: 260, ease: 'Back.easeOut' });
        this.fx.sparkles(pad.x, pad.y - pad.h, 0xdff4ff, 8);
      }
    }
  }

  /** Olaf's snowballs: a tiny texture made once. */
  makeSnowball() {
    if (this.textures.exists('snowball')) return;
    const g = this.make.graphics({ x: 0, y: 0, add: false });
    g.fillStyle(0x1a121e).fillCircle(4, 4, 4);
    g.fillStyle(0xeef8ff).fillCircle(4, 4, 3);
    g.fillStyle(0xffffff).fillRect(3, 2, 2, 2);
    g.generateTexture('snowball', 8, 8);
    g.destroy();
  }

  updateParallax() {
    const cam = this.cameras.main, W = GAME.WORLD.width;
    const maxX = Math.max(1, this.levelW - W), maxY = this.levelH - GAME.WORLD.height;
    this.bgFar.x = -Math.round((this.bgFar.width - W) * Phaser.Math.Clamp(cam.scrollX / maxX, 0, 1));
    // Slides down at most 10px as the camera climbs, never past its top edge.
    this.bgFar.y = Math.round(10 * Phaser.Math.Clamp((maxY - cam.scrollY) / Math.max(1, maxY), 0, 1)) - 10;
    this.bgMid.tilePositionX = Math.round(cam.scrollX * 0.3);
    this.bgMid.y = Math.round((maxY - cam.scrollY) * 0.2);
  }

  updateAnim(onGround) {
    const c = this.char, p = this.player;
    if (this.sealing) return;            // seal() holds the Keyblade-raised pose
    if (this.swing) {
      p.anims.stop();
      const f = this.swing.gen ? Math.max(0, this.slashFrame(this.time.now - this.swing.start)) : 0;
      p.setTexture(GAME.sheetKey(c, 'attack'), f);
      return;
    }
    if (!onGround) {
      p.anims.stop();
      p.setTexture(GAME.sheetKey(c, 'jump'), this.jumpFrame(p.body.velocity.y));
    } else if (this.landTimer > 0) {
      p.anims.stop();
      p.setTexture(GAME.sheetKey(c, 'jump'), GAME.LAND_FRAME);
    } else if (Math.abs(p.body.velocity.x) > 10) {
      p.play(GAME.animKey(c, 'run'), true);
    } else {
      p.play(GAME.animKey(c, 'idle'), true);
    }
  }

  jumpFrame(vy) {
    const n = vy / GAME.MOVE.jump;
    for (const [bound, f] of GAME.JUMP_FRAMES) if (n <= bound) return f;
    return 5;
  }

  // --- Keyblade ---------------------------------------------------------------
  hand() {
    const c = this.char, p = this.player;
    return { x: p.x + this.facing * c.hand[0], y: p.y + c.hand[1] };
  }

  startSwing(time) {
    const c = this.char, p = this.player;
    this.swing = { start: time, hit: new Set(), gen: c.generatedAttack };
    // The Keyblade is summoned.
    if (c.generatedAttack) this.fx.sparkles(p.x + this.facing * 12, p.y - c.figure[1] * 0.6, c.tint, 4);
    else { const h = this.hand(); this.fx.sparkles(h.x, h.y, c.tint, 4); }
  }

  /** Which frame of a generated slash shows t ms into the swing; -1 when done. */
  slashFrame(t) {
    const ms = GAME.COMBAT.slashMs;
    let acc = 0;
    for (let i = 0; i < ms.length; i++) { acc += ms[i]; if (t < acc) return i; }
    return -1;
  }

  /** Everything in front of the kid, feet to above the head, out to 'reach'. */
  swingHits(s, reach) {
    const p = this.player, f = this.facing;
    const back = p.x - f * 6;
    const top = p.y - this.char.figure[1] - 8;
    const r = new Phaser.Geom.Rectangle(f > 0 ? back : back - reach - 6, top, reach + 6, p.y + 4 - top);
    for (const e of this.enemies) {
      if (e.solid && !s.hit.has(e) && Phaser.Geom.Intersects.RectangleToRectangle(r, e.bounds())) {
        s.hit.add(e); e.hit(f);
        this.cameras.main.shake(70, 0.004);
      }
    }
  }

  updateSwing(time) {
    const s = this.swing, C = GAME.COMBAT;
    if (this.sealing) return;            // the raised Keyblade stays up for the beam
    if (!s) { this.blade.setVisible(false); this.swoosh.setVisible(false); return; }
    const t = time - s.start;
    if (s.gen) {
      // A drawn slash: ready -> wind-up -> strike -> follow-through. The hit
      // lands on the strike frame, with a swoosh trailing the blade.
      this.blade.setVisible(false);
      const ms = C.slashMs, total = ms.reduce((a, b) => a + b, 0);
      if (t >= total) { this.swing = null; this.swoosh.setVisible(false); return; }
      const strikeAt = ms.slice(0, C.hitFrame).reduce((a, b) => a + b, 0);
      const from = strikeAt - C.hitLead, to = strikeAt + ms[C.hitFrame] + (ms[C.hitFrame + 1] || 0) / 2;
      const p = this.player, f = this.facing, fig = this.char.figure[1];
      if (t >= from) {
        const sc = Phaser.Math.Clamp(fig / 66, 0.6, 1);
        this.swoosh.setVisible(true)
          .setPosition(Math.round(p.x + f * 6 * sc), Math.round(p.y - fig * 0.55))
          .setScale(f * sc, sc).setAlpha(Math.max(0, 1 - (t - from) / (total - from)));
      } else this.swoosh.setVisible(false);
      if (t >= from && t <= to) this.swingHits(s, this.char.attackReach);
      return;
    }
    if (t >= C.swingMs) { this.swing = null; this.updateSwing(time); return; }
    const h = this.hand(), f = this.facing;
    const k = Math.min(1, t / 190), ease = 1 - Math.pow(1 - k, 3);
    const theta = -125 + 180 * ease;                      // raised behind -> forward-down
    this.blade.setVisible(true).setPosition(Math.round(h.x), Math.round(h.y))
      .setScale(f, 1).setAngle(f * theta);
    if (t > 35) {
      this.swoosh.setVisible(true).setPosition(Math.round(h.x), Math.round(h.y)).setScale(f, 1)
        .setAlpha(Math.max(0, 1 - (t - 35) / (C.swingMs - 60)));
    }
    // Centring the hit box on the hand let tall kids swing clean over a
    // Shadow's head (Sara's grip is 50px up, a Shadow is 18px tall), so it
    // covers the kid's whole height.
    if (t >= C.hitFrom && t <= C.hitTo) this.swingHits(s, C.reach.w);
  }

  // --- damage -----------------------------------------------------------------
  checkEnemyContact(time) {
    const p = this.player, b = p.body;
    const pr = new Phaser.Geom.Rectangle(b.x, b.y, b.width, b.height);
    for (const e of this.enemies) {
      if (!e.solid) continue;
      const er = e.bounds();
      if (!Phaser.Geom.Intersects.RectangleToRectangle(pr, er)) continue;
      // Landing on top defeats it and bounces you -- you never need the button.
      if (b.velocity.y > 30 && b.bottom - er.top < 14) {
        e.hit(p.x < e.sprite.x ? 1 : -1);
        b.setVelocityY(-(this.controls.held('jump') ? GAME.MOVE.jump * 0.9 : GAME.COMBAT.stompBounce));
        this.jumpCut = this.controls.held('jump');
      } else if (e.harmful) {
        this.hurt(e.sprite.x, time);
      }
    }
  }

  hurt(fromX, time) {
    if (time < this.invulnUntil || this.busy) return;
    const C = GAME.COMBAT, b = this.player.body;
    this.hearts = Math.max(0, this.hearts - 1);
    this.drawHearts();
    this.invulnUntil = time + C.hurtMs;
    this.knockUntil = time + 260;
    this.swing = null;
    const dir = this.player.x < fromX ? -1 : 1;
    b.setVelocity(dir * C.knockX, -C.knockY);
    this.cameras.main.shake(120, 0.006);
    if (this.hearts <= 0) this.faint();
  }

  fellInPit() {
    this.hearts = Math.max(0, this.hearts - 1);
    if (this.hearts <= 0) this.hearts = GAME.COMBAT.hearts;
    this.backToSave();
  }

  faint() {
    this.hearts = GAME.COMBAT.hearts;
    this.backToSave();
  }

  /** Fade, reappear at the last save point, fade back in. */
  backToSave() {
    this.busy = true;
    const cam = this.cameras.main;
    cam.fadeOut(260, 0, 0, 0);
    cam.once('camerafadeoutcomplete', () => {
      const p = this.player;
      p.setPosition(this.respawn.x, this.respawn.y - 1);
      p.body.setVelocity(0, 0);
      this.swing = null;
      this.drawHearts();
      this.invulnUntil = this.time.now + 1000;
      this.friend.reset(p.x, p.y);
      cam.fadeIn(300, 0, 0, 0);
      this.busy = false;
    });
  }

  // --- pickups ------------------------------------------------------------------
  addPickup(kind, x, y) {
    const img = this.add.image(x, y, kind === 'munny' ? 'munny' : 'heart', 0).setDepth(5);
    this.tweens.add({ targets: img, y: y - 2, duration: 600 + Math.random() * 200, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' });
    if (kind === 'munny') this.tweens.add({ targets: img, scaleX: 0.35, duration: 380, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' });
    const pk = { kind, img, live: true, readyAt: 0 };
    this.pickups.push(pk);
    return pk;
  }

  /** A munny popping out of a defeated Heartless. */
  dropMunny(x, y) {
    const pk = this.addPickup('munny', x, y);
    pk.readyAt = this.time.now + 300;
    this.tweens.killTweensOf(pk.img);
    this.tweens.add({ targets: pk.img, y: y - 18, duration: 180, ease: 'Quad.easeOut', yoyo: true,
      onComplete: () => this.tweens.add({ targets: pk.img, scaleX: 0.35, duration: 380, yoyo: true, repeat: -1 }) });
  }

  /** A heart tossed by the Disney friend, landing near the kid. */
  dropHeart(x, y, towardX) {
    const pk = this.addPickup('heart', x, y);
    pk.readyAt = this.time.now + 250;
    this.tweens.killTweensOf(pk.img);
    const tx = x + Phaser.Math.Clamp(towardX - x, -40, 40);
    this.tweens.add({ targets: pk.img, x: tx, duration: 420 });
    this.tweens.add({ targets: pk.img, y: y - 22, duration: 210, yoyo: true, ease: 'Quad.easeOut' });
  }

  checkPickups() {
    const b = this.player.body, now = this.time.now;
    const cx = b.center.x, cy = b.center.y;
    for (const pk of this.pickups) {
      if (!pk.live || now < pk.readyAt) continue;
      if (Math.abs(pk.img.x - cx) < b.width / 2 + 7 && Math.abs(pk.img.y - cy) < b.height / 2 + 7) {
        pk.live = false;
        if (pk.kind === 'munny') { this.munny++; this.munnyText.setText('x' + this.munny); this.fx.sparkles(pk.img.x, pk.img.y, 0xffd23f, 5); }
        else { this.hearts = Math.min(GAME.COMBAT.hearts, this.hearts + 1); this.drawHearts(); this.fx.sparkles(pk.img.x, pk.img.y, 0xff7fb2, 8); }
        this.tweens.killTweensOf(pk.img);
        this.tweens.add({ targets: pk.img, y: pk.img.y - 10, alpha: 0, duration: 200, onComplete: () => pk.img.destroy() });
      }
    }
    this.pickups = this.pickups.filter(p => p.live);
  }

  // --- save points --------------------------------------------------------------
  addSave(x, y) {
    const ring = this.add.sprite(x, y + 5, this.world.id + '-savepoint', 0).setOrigin(0.5, 1).setDepth(4);
    const bw = Math.round(ring.width * 0.62);
    const beam = this.add.rectangle(x, y - ring.height * 0.35, bw, 80, 0x9fb4ff, 0.10).setOrigin(0.5, 1).setDepth(3);
    this.tweens.add({ targets: beam, alpha: 0.2, duration: 900, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' });
    this.saves.push({ x, y, ring, beam, on: false, nextRise: 0 });
  }

  checkSaves(time) {
    const p = this.player;
    for (const s of this.saves) {
      if (time > s.nextRise) { this.fx.rise(s.x, s.y - 4, s.on ? 0x7cffb8 : 0x9fb4ff); s.nextRise = time + 260; }
      if (!s.on && Math.abs(p.x - s.x) < 16 && Math.abs(p.y - s.y) < 20) {
        s.on = true;
        s.ring.setFrame(1);
        s.beam.setFillStyle(0x7cffb8, 0.16);
        this.respawn = { x: s.x, y: s.y };
        this.hearts = GAME.COMBAT.hearts; this.drawHearts();      // save points heal, like in KH
        this.fx.sparkles(s.x, s.y - 20, 0x7cffb8, 14);
        this.fx.say(s.x, s.y - 60, 'SAVED!');
      }
    }
  }

  // --- the Keyhole --------------------------------------------------------------
  addKeyhole(x, y) {
    // Floats a little above the ground, its bottom tip about 30px up.
    const k = this.add.image(x, 0, this.world.id + '-keyhole').setDepth(4);
    k.y = Math.round(y - 30 - k.height / 2);
    this.tweens.add({ targets: k, y: k.y - 4, duration: 1100, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' });
    this.tweens.add({ targets: k, alpha: 0.8, duration: 600, yoyo: true, repeat: -1 });
    this.keyhole = { x, y, img: k, nextRise: 0 };
  }

  checkKeyhole() {
    const k = this.keyhole, p = this.player;
    if (!k) return;
    if (this.time.now > k.nextRise) { this.fx.rise(k.x, k.y - 30, 0xffd25a); k.nextRise = this.time.now + 200; }
    // No need to land exactly on it: passing by, even mid-jump, counts.
    if (Math.abs(p.x - k.x) < 36 && Math.abs(p.y - k.y) < 70) this.seal();
  }

  /** The kid raises the Keyblade, a beam locks the Keyhole, the world is safe. */
  seal() {
    const k = this.keyhole, p = this.player, c = this.char;
    this.busy = true; this.sealing = true; this.swing = null;
    this.facing = k.x >= p.x ? 1 : -1;
    p.body.setVelocity(0, 0);
    p.anims.stop(); p.setTexture(GAME.sheetKey(c, 'attack'), 0).setFlipX(this.facing < 0);
    let tip;
    if (c.generatedAttack) {
      // The ready pose already holds the Keyblade up: the beam leaves its tip.
      this.swoosh.setVisible(false);
      tip = { x: p.x + this.facing * c.bladeTip[0], y: p.y + c.bladeTip[1] };
    } else {
      const h = this.hand();
      this.blade.setVisible(true).setPosition(Math.round(h.x), Math.round(h.y))
        .setScale(this.facing, 1).setAngle(this.facing * -55);
      tip = { x: h.x + this.facing * 15, y: h.y - 22 };
    }
    const target = { x: k.img.x, y: k.img.y };
    const beam = this.add.graphics().setDepth(18);
    const prog = { t: 0 };
    this.tweens.add({
      targets: prog, t: 1, duration: 700, ease: 'Quad.easeIn',
      onUpdate: () => {
        beam.clear();
        const ex = tip.x + (target.x - tip.x) * prog.t, ey = tip.y + (target.y - tip.y) * prog.t;
        beam.lineStyle(5, c.tint, 0.5).lineBetween(tip.x, tip.y, ex, ey);
        beam.lineStyle(2, 0xffffff, 1).lineBetween(tip.x, tip.y, ex, ey);
      },
      onComplete: () => {
        this.fx.sparkles(target.x, target.y, 0xffffff, 20);
        this.cameras.main.flash(500, 255, 250, 220);
        // Stop the idle pulse first, or its repeating alpha tween keeps the
        // Keyhole fully visible through the fade.
        this.tweens.killTweensOf(k.img);
        this.tweens.add({ targets: k.img, scale: 2.4, alpha: 0, duration: 600 });
        // A sealed world is a safe world: every Heartless left lets go of its heart.
        this.enemies.filter(e => e.alive).forEach((e, i) =>
          this.time.delayedCall(120 + i * 140, () => e.defeat()));
        this.time.delayedCall(700, () => { beam.destroy(); this.showSealed(); });
      },
    });
  }

  showSealed() {
    const W = GAME.WORLD.width, H = GAME.WORLD.height;
    const L = (o) => o.setScrollFactor(0).setDepth(2000);
    L(this.add.rectangle(0, 0, W, H, 0x120a1e, 0.72).setOrigin(0));
    const t1 = L(GAME.text(this, W / 2, 104, 'WORLD SEALED!', 16, '#fff3d0').setOrigin(0.5, 0)).setStroke('#7a3a1a', 4);
    L(GAME.text(this, W / 2, 132, this.world.name.toUpperCase(), 8, '#ffd27c').setOrigin(0.5, 0));
    L(this.add.image(W / 2 - 20, 166, 'munny').setScale(2));
    L(GAME.text(this, W / 2 - 4, 162, 'x' + this.munny, 8, '#ffffff'));
    GAME.progress.seal(this.world.id);
    const go = L(GAME.text(this, W / 2, 214, 'TAP TO CONTINUE', 8, '#fff3d0').setOrigin(0.5, 0));
    this.tweens.add({ targets: t1, scale: 1.08, duration: 500, yoyo: true, repeat: -1 });
    this.tweens.add({ targets: go, alpha: 0.3, duration: 600, yoyo: true, repeat: -1 });
    this.time.delayedCall(700, () => {
      const next = () => this.scene.start('worlds', { characterId: this.char.id });
      this.input.once('pointerdown', next);
      this.input.keyboard.once('keydown-SPACE', next);
    });
  }

  // --- hud ------------------------------------------------------------------------
  buildHud() {
    const W = GAME.WORLD.width;
    this.heartIcons = [];
    for (let i = 0; i < GAME.COMBAT.hearts; i++) {
      this.heartIcons.push(this.add.image(8 + i * 13, 8, 'heart', 0).setOrigin(0).setScrollFactor(0).setDepth(1000));
    }
    this.add.image(8, 24, 'munny').setOrigin(0).setScrollFactor(0).setDepth(1000);
    this.munnyText = GAME.text(this, 20, 24, 'x0', 8, '#ffffff').setScrollFactor(0).setDepth(1000).setStroke('#2a1220', 3);
    const menu = GAME.text(this, W - 8, 8, 'MENU', 8, '#fff3d0').setOrigin(1, 0)
      .setScrollFactor(0).setDepth(1000).setStroke('#2a1220', 3).setInteractive({ useHandCursor: true });
    menu.on('pointerdown', () => this.scene.start('worlds', { characterId: this.char.id }));
  }

  drawHearts() {
    this.heartIcons.forEach((h, i) => h.setFrame(i < this.hearts ? 0 : 1));
  }
};
