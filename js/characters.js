/* ---------------------------------------------------------------------------
 * Roster + world tuning.
 *
 * This is the ONLY place a character is described. The preloader, the select
 * screen and the animation registration all iterate GAME.CHARACTERS, so adding a
 * kid is one block here plus a run of the art pipeline.
 *
 * Sizes are no longer here. With real pixel art nothing may be scaled at
 * runtime -- every sprite is drawn 1:1 or the pixels stop matching -- so the
 * hand-tuned sizes moved into art/pixel_spec.json, and cell / anchor / figure /
 * Keyblade grip are read from art/pixel/manifest.json, which tools/pixelize.py
 * writes.
 * ------------------------------------------------------------------------- */
window.GAME = window.GAME || {};

GAME.WORLD = {
  width: 640,          // the pixel-art screen; Scale.FIT blows it up to the phone
  height: 360,
  tile: 16,
  gravity: 1250,
  maxFall: 620,
};

/* Everyone moves the same. With per-kid jump strength, Baltazar cleared half
 * the gap Pedro did, so any level fair to one was impossible or trivial for
 * another. The kids differ in how they look, not in how far they can jump. */
GAME.MOVE = {
  speed: 165,          // px/s
  jump: 520,           // launch speed -> ~108px (6.7 tiles) at full height
  jumpCut: 0.45,       // releasing jump early multiplies the rise by this
  coyoteMs: 90,        // can still jump this long after running off a ledge
  bufferMs: 110,       // a jump pressed this long before landing still fires
};

GAME.COMBAT = {
  hearts: 4,
  hurtMs: 1300,        // invulnerable after a hit
  knockX: 150, knockY: 250,
  // Keyblade swing. With a generated slash the sheet's frames are spread over
  // the swing: ready -> wind-up -> strike -> follow-through, and the strike is
  // held a moment so the hit reads. Frame times in ms, one per sheet frame.
  slashMs: [40, 70, 110, 90],
  hitFrame: 2,               // the strike: the swing connects while it shows
  hitLead: 20,               // ...starting this long before it, so it feels instant
  swingMs: 300,        // old overlay swing (no generated slash)
  hitFrom: 40, hitTo: 210,
  reach: { w: 42 },          // hit box depth in front of the kid; height = the kid
  stompBounce: 360,
};

/* Enemies. The challenge is the platforming; enemies are easy to read and
 * easy to beat. Every attack has a long, visible tell, and a hyena that's been
 * hit once stands dizzy (and harmless) long enough for the second hit. */
GAME.SHADOW = {
  walk: 26, chase: 40,
  lungeRange: 56,        // hops at a kid this close, on the same level
  windupMs: 750,         // the crouch before it -- the kid's cue
  lungeMs: 240, lungeSpeed: 140,
  lungeEvery: 3400,
};
GAME.HYENA = {
  walk: 30,
  sight: 130,            // spots a kid this far away on its own level
  windupMs: 900,         // flashes and crouches, then...
  chargeMs: 480, charge: 165,
  restMs: 1600,          // pants after a charge -- the moment to hit it
  cooldownMs: 3600,
  hp: 2,
  dizzyMs: 1800,         // after the first hit: harmless, waiting for the second
};

/* Velocity-driven jump frames (unchanged from milestone 1). vy is normalised
 * against the launch speed: -1 = takeoff, 0 = apex, +1 = falling fast.
 * Sheet: f0 crouch, f1-f2 rising, f3 tucked apex, f4 descending, f5 landing. */
GAME.JUMP_FRAMES = [
  [-0.55, 1],
  [-0.18, 2],
  [ 0.18, 3],
  [ 0.60, 4],
  [ Infinity, 5],
];
GAME.LAND_FRAME = 0;
GAME.LAND_MS = 90;

GAME.CHARACTERS = [
  { id: 'baltazar',  name: 'Baltazar',  folder: 'Baltazar',  tint: 0xffb347,
    anims: { idle: { fps: 6 }, run: { fps: 11 }, jump: {}, attack: {} } },
  { id: 'francisco', name: 'Francisco', folder: 'Francisco', tint: 0xffb347,
    anims: { idle: { fps: 6 }, run: { fps: 12 }, jump: {}, attack: {} } },
  { id: 'jo',        name: 'Jo',        folder: 'Jo',        tint: 0x7fd4ff,
    anims: { idle: { fps: 6 }, run: { fps: 12 }, jump: {}, attack: {} } },
  { id: 'olimpia',   name: 'Olimpia',   folder: 'Olimpia',   tint: 0x7fd4ff,
    anims: { idle: { fps: 6 }, run: { fps: 12 }, jump: {}, attack: {} } },
  { id: 'pedro',     name: 'Pedro',     folder: 'Pedro',     tint: 0xffb347,
    anims: { idle: { fps: 6 }, run: { fps: 12 }, jump: {}, attack: {} } },
  { id: 'sara',      name: 'Sara',      folder: 'Sara',      tint: 0x7fd4ff,
    anims: { idle: { fps: 6 }, run: { fps: 12 }, jump: {}, attack: {} } },
];

/* Worlds, in order. Each has its own art folder (tools/build_gen_art.py),
 * level text, Disney friend and charging enemy (level letter 'Y'). `thumb` is
 * the corner of the window onto its far background shown on the world map. */
GAME.WORLDS = [
  { id: 'pride', name: 'Pride Lands', level: 'levels/pride_lands.txt', art: 'art/world/pride',
    friend: 'simba', charger: 'hyena', thumb: [470, 160] },
  { id: 'arendelle', name: 'Arendelle', level: 'levels/arendelle.txt', art: 'art/world/arendelle',
    friend: 'olaf', charger: 'wolf', thumb: [475, 40] },
  { id: 'seoul', name: 'Neon Seoul', level: 'levels/neon_seoul.txt', art: 'art/world/seoul',
    friend: 'derpy', charger: 'demon', thumb: [128, 81] },
  { id: 'spider', name: 'Spider City', level: 'levels/spider_city.txt', art: 'art/world/spider',
    friend: null, charger: 'goblin', thumb: [128, 46] },     // here the kid is the web-swinger, on their own
];

/* The Disney friends. 'pounce' leaps onto the enemy; 'throw' lobs a snowball. */
GAME.FRIENDS = {
  simba: { help: 'pounce', shout: 'RAWR!', heart: 'ROAR!' },
  olaf:  { help: 'throw', shout: 'SNOWBALL!', heart: 'WARM HUGS!' },
  derpy: { help: 'pounce', shout: 'RAWR!', heart: 'TIGER HUG!' },
};

/* Charging enemies (GAME.Hyena behaviour) and what they say. */
GAME.CHARGERS = {
  hyena: { growl: 'GRR!', beaten: 'YIP!' },
  wolf:  { growl: 'GRRR!', beaten: 'AWOO!' },
  demon: { growl: 'HEHEHE!', beaten: 'EEEK!' },
  goblin: { growl: 'BZZT!', beaten: 'BOING!' },
};

/* World 2 toys. */
GAME.BOUNCE = 690;          // snow bounce pad launch speed (~190px high)
GAME.CRUMBLE = { shakeMs: 650, goneMs: 2600 };
GAME.ICE = { grip: 0.06 };  // on slippery ice, speed moves this much toward the target per frame

/* World 3: beat platforms come and go with the music, four beats to a bar.
 * Group 1 is gone on beat 4, group 2 on beat 2 -- never both at once, and
 * each blinks for a whole beat before it goes. */
GAME.BEAT = { beatMs: 750, on: { 1: [1, 1, 1, 0], 2: [1, 0, 1, 1] } };

/* World 4: web anchors. Jump near one and the kid grabs the web by
 * themselves, swings forward and is flung on -- no button needed (jump lets
 * go early). reach: how far from the anchor a grab works; the swing runs
 * from wherever you grabbed to endAngle (radians past straight down). */
GAME.WEB = { reach: 150, minLen: 56, maxLen: 136, swingMs: 620, endAngle: 0.95,
  fling: [230, -330], cooldownMs: 600 };

GAME.byId = function (id) {
  return GAME.CHARACTERS.find(function (c) { return c.id === id; });
};

/* Texture keys are derived, never hand-written, so they cannot drift. */
GAME.sheetKey = function (c, anim) { return c.id + '-' + anim; };
GAME.portraitKey = function (c) { return c.id + '-portrait'; };
GAME.animKey = function (c, anim) { return c.id + '-' + anim + '-anim'; };

GAME.FONT = '"Press Start 2P", monospace';

/** A button a small finger can hit on a phone: a rounded panel with a label
 *  (and an optional icon image), and an invisible tap zone `pad` px bigger on
 *  every side than what you see. Fixed to the screen. Returns its parts. */
GAME.button = function (scene, x, y, w, h, label, onTap, opts = {}) {
  const depth = opts.depth || 1000, pad = opts.pad !== undefined ? opts.pad : 12;
  const g = scene.add.graphics().setScrollFactor(0).setDepth(depth);
  const draw = (down) => {
    g.clear();
    g.fillStyle(down ? 0x5a3a7a : 0x2a1a3e, opts.alpha !== undefined ? opts.alpha : 0.85);
    g.fillRoundedRect(x - w / 2, y - h / 2, w, h, 6);
    g.lineStyle(2, 0xffd27c, 1).strokeRoundedRect(x - w / 2, y - h / 2, w, h, 6);
  };
  draw(false);
  const parts = [g];
  let tx = x;
  if (opts.icon) {
    const icon = scene.add.image(x - w / 2 + 6 + (opts.iconW || 20) / 2, y, opts.icon)
      .setScale(opts.iconScale || 1).setScrollFactor(0).setDepth(depth + 1);
    parts.push(icon);
    tx = x + (opts.iconW || 20) / 2;
  }
  const t = GAME.text(scene, tx, y, label, opts.size || 8, '#fff3d0').setOrigin(0.5)
    .setScrollFactor(0).setDepth(depth + 1);
  parts.push(t);
  const zone = scene.add.zone(x, y, w + pad * 2, h + pad * 2).setScrollFactor(0).setDepth(depth + 2)
    .setInteractive({ useHandCursor: true });
  zone.on('pointerdown', () => draw(true));
  zone.on('pointerout', () => draw(false));
  zone.on('pointerup', () => { draw(false); onTap(); });
  parts.push(zone);
  return { parts, zone, destroy: () => parts.forEach(o => o.destroy()) };
};
GAME.text = function (scene, x, y, str, size, color) {
  return scene.add.text(Math.round(x), Math.round(y), str, {
    fontFamily: GAME.FONT, fontSize: (size || 8) + 'px', color: color || '#ffffff',
  });
};
