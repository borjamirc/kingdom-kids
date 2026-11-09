/* ---------------------------------------------------------------------------
 * Playtest bot -- a developer tool, never loaded by the game.
 *
 * In the browser console on the running game (select screen showing):
 *
 *   await import('./tools/playtest.js')      // or add a <script> tag by hand
 *   PT.start()                               // take over the game clock
 *   PT.run('pedro')                          // play the current world with a bot
 *   PT.run('jo', { world: 'arendelle' })     // ...or another world
 *   PT.run('sara', { passive: true })        // ...one that never attacks
 *   const done = PT.friendStats(); PT.run('jo'); done()   // how Simba coped
 *
 * PT.start() stops the real-time loop and steps the game by hand, 60 steps per
 * simulated second, with Date.now() following the simulated clock (tweens use
 * it). Reload the page to get the normal game back.
 *
 * The bot runs right, jumps at walls and gaps, swings at enemies, waits for
 * moving platforms and rides the elevator. It reports how far it got, falls,
 * hearts lost and how long it took.
 * ------------------------------------------------------------------------- */
window.PT = (() => {
  let t = 0, off = 0;
  const realNow = Date.now.bind(Date);

  function start(characterId = 'olimpia', worldId = GAME.WORLDS[0].id) {
    t = performance.now() + 1e6; off = 0;
    Date.now = () => realNow() + off;
    GAME.game.loop.stop();
    const from = GAME.game.scene.getScenes(true)[0];
    from.scene.start('play', { characterId, worldId });
    step(3);
    return 'ok';
  }

  function step(n = 1) {
    for (let i = 0; i < n; i++) { t += 16.667; off += 16.667; GAME.game.step(t, 16.667); }
    return GAME.game.scene.getScene('play');
  }

  /** Replace the controls with a function returning {left,right,jump,attack}. */
  function drive(s, want) {
    s.controls.update = function () {
      this.prev = this.state;
      this.state = Object.assign({ left: false, right: false, jump: false, attack: false }, want());
      this.consumed = {};
    };
  }

  function run(characterId, opts = {}) {
    const maxFrames = opts.frames || 9000;
    let s = GAME.game.scene.getScene('play');
    const worldId = opts.world || (s.world && s.world.id) || GAME.WORLDS[0].id;
    s.scene.restart({ characterId, worldId }); step(2);
    s = GAME.game.scene.getScene('play');
    const L = s.layer, T = GAME.WORLD.tile;
    const solidAt = (x, y) => { const tl = L.getTileAtWorldXY(x, y); return !!(tl && tl.index >= 0); };
    const wallAt = (x, y) => { const tl = L.getTileAtWorldXY(x, y); return !!(tl && tl.index >= 0 && tl.index <= GAME.Level.SOLID_MAX); };
    // Floor = tiles, or a crumbling ice platform that's still there.
    const crumbleAt = (x, y) => s.crumbles.some(k => k.state !== 'gone' && x >= k.sprite.x && x <= k.sprite.x + k.sprite.width && y >= k.sprite.y && y <= k.sprite.y + 16);
    const floorAhead = (x, y) => { for (let dy = 4; dy < 7 * T; dy += 8) if (solidAt(x, y + dy) || crumbleAt(x, y + dy)) return true; return false; };
    let frame = 0, hurts = 0, falls = 0, hits = 0, jumpHold = 0, useElev = null;
    const log = [];
    const hurt = s.hurt.bind(s);
    s.hurt = (x, tm) => { if (tm >= s.invulnUntil && !s.busy) hurts++; hurt(x, tm); };
    const pit = s.fellInPit.bind(s);
    s.fellInPit = () => { falls++; log.push(frame + ': fell at x=' + Math.round(s.player.x)); pit(); };
    s.enemies.forEach(e => { const h = e.hit.bind(e); e.hit = d => { hits++; h(d); }; });

    drive(s, () => {
      const p = s.player, b = p.body, onG = b.blocked.down || b.touching.down;
      const press = {};
      const e = s.enemies.filter(e => e.alive && e.solid && e.sprite.x > p.x - 16 &&
        e.sprite.x - p.x < 90 && Math.abs(e.sprite.y - p.y) < 30).sort((a, c) => a.sprite.x - c.sprite.x)[0];
      const d = e ? e.sprite.x - p.x : 999;
      if (!opts.passive && e && d < s.char.attackReach + 6 && !s.swing && frame % 3 === 0) press.attack = true;
      // A closed chest within reach: open it (passive bots too -- that's no fight).
      const chest = s.chests.find(c => !c.open && Math.abs(c.x - p.x) < s.char.attackReach && Math.abs(c.y - p.y) < 30);
      if (chest && !s.swing && frame % 3 === 0) { press.attack = true; s.facing = chest.x >= p.x ? 1 : -1; }
      const riding = s.movers.find(m => m.riding(b));
      if (riding) {
        if (riding.dy) {                                  // elevator: off at the top
          useElev = null;
          const top = Math.abs(riding.sprite.y - (riding.y0 + riding.dy)) < 6;
          press.right = top;
          if (top && jumpHold === 0) jumpHold = 10;
        } else {                                          // slider: off at the far end
          const k = (riding.sprite.x - riding.x0) / riding.dx;
          if (k > 0.9 && jumpHold === 0) jumpHold = 22;
          press.right = k > 0.9 || jumpHold > 0;
        }
      } else {
        press.right = !(e && d < 40 && onG);
        // Over a moving platform in the air: let go of right and drop onto it.
        const below = s.movers.find(m => p.x > m.sprite.x + 10 && p.x < m.sprite.x + m.sprite.width - 10 &&
          m.sprite.y > p.y - 4 && m.sprite.y - p.y < 120);
        if (!onG && below && b.velocity.y > 0) press.right = false;
        const wall = wallAt(p.x + 20, p.y - 8) || wallAt(p.x + 20, p.y - 24);
        const tall = wall && wallAt(p.x + 20, p.y - 6 * T);
        const gap = onG && !floorAhead(p.x + 30, p.y);
        const elev = s.movers.find(m => m.dy && Math.abs(m.sprite.x + m.sprite.width / 2 - p.x) < 320);
        // A bounce pad just behind a wall too tall to jump: step back onto it.
        const pad = s.bounces.find(pd => pd.x < p.x && p.x - pd.x < 80);
        if (tall && !elev && pad && onG) { press.right = false; press.left = true; }
        if (tall && elev) useElev = elev;
        if (useElev) {
          const elev = useElev;
          const cx = elev.sprite.x + elev.sprite.width / 2, atBottom = Math.abs(elev.sprite.y - elev.y0) < 6;
          press.right = p.x < cx - 12; press.left = p.x > cx + 12;
          if (Math.abs(p.x - cx) < 20 && atBottom && onG && jumpHold === 0) jumpHold = 8;
        } else if (gap) {
          const slider = s.movers.find(m => m.dx && m.sprite.x > p.x - 40 && m.sprite.x - p.x < 220);
          if (slider) {
            const near = slider.sprite.x - (p.x + 12) < 76;
            press.right = false;
            if (near && jumpHold === 0) jumpHold = 18;
            if (jumpHold > 0) press.right = true;
          } else if (jumpHold === 0) jumpHold = 22;
        } else if (onG && wall && jumpHold === 0) jumpHold = 22;
      }
      if (jumpHold > 0) { press.jump = true; jumpHold--; }
      return press;
    });

    let sealedAt = -1, maxX = 0;
    for (let i = 0; i < maxFrames; i++) {
      frame = i; step(1);
      maxX = Math.max(maxX, s.player.x);
      if (s.sealing) { sealedAt = i; break; }
    }
    return {
      characterId, sealed: sealedAt >= 0, secs: +(frame / 60).toFixed(1),
      x: Math.round(s.player.x), maxX: Math.round(maxX), levelW: s.levelW,
      hurts, falls, hits, coins: s.coinPct() + '%',
      chests: s.chests.filter(c => c.open).map(c => c.index).join(',') || '-', log: log.slice(0, 10),
    };
  }

  /** Start measuring the Disney friend; call the returned function for the
   *  numbers: % of time in the air, % overlapping the kid, jumps, puffs,
   *  distance to the kid (median / 90th percentile). */
  function friendStats() {
    const st = { frames: 0, air: 0, overlap: 0, poofs: 0, jumps: 0, dist: [], run: 0, maxRun: 0, poofAt: [] };
    let hooked = null;
    const fn = () => {
      const sc = GAME.game.scene.getScene('play'), f = sc && sc.friend;
      if (!f || !f.sprite.body) return;
      if (hooked !== f) {
        hooked = f;
        const poof = f.poof.bind(f);
        f.poof = p => { const x = Math.round(f.sprite.x), r = poof(p); if (r) { st.poofs++; st.poofAt.push(x); } return r; };
        const jump = f.jump.bind(f);
        f.jump = (tg, tm) => { st.jumps++; jump(tg, tm); };
      }
      if (f.state !== 'follow' || sc.busy) return;
      const b = f.sprite.body, p = sc.player;
      st.frames++;
      if (!(b.blocked.down || b.touching.down)) { st.air++; st.run++; st.maxRun = Math.max(st.maxRun, st.run); } else st.run = 0;
      if (Math.abs(f.sprite.x - p.x) < 20 && Math.abs(f.sprite.y - p.y) < 20) st.overlap++;
      if (st.frames % 30 === 0) st.dist.push(Math.round(Math.hypot(f.sprite.x - p.x, f.sprite.y - p.y)));
    };
    GAME.game.events.on('poststep', fn);
    return () => {
      GAME.game.events.off('poststep', fn);
      const d = st.dist.slice().sort((a, c) => a - c);
      return {
        airPct: +(100 * st.air / st.frames).toFixed(1), longestAirFrames: st.maxRun,
        overlapPct: +(100 * st.overlap / st.frames).toFixed(1), jumps: st.jumps, poofs: st.poofs,
        poofAt: st.poofAt.slice(0, 12), distMedian: d[d.length >> 1], distP90: d[Math.floor(d.length * 0.9)],
      };
    };
  }

  return { start, step, drive, run, friendStats };
})();
