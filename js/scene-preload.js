/* ---------------------------------------------------------------------------
 * Preload: every sprite, the world art and the level text.
 *
 * Real pixel art is tiny -- all six kids plus every world come to about a
 * megabyte -- so everything loads once here and picking a kid or a world is
 * instant. (Milestone 1 loaded several MB per kid, at play time.)
 * ------------------------------------------------------------------------- */
window.GAME = window.GAME || {};

GAME.PreloadScene = class PreloadScene extends Phaser.Scene {
  constructor() { super('preload'); }

  preload() {
    const W = GAME.WORLD.width, H = GAME.WORLD.height;
    const bw = 240, bx = (W - bw) / 2, by = H / 2;
    this.add.rectangle(bx, by, bw, 6, 0x2a2440).setOrigin(0);
    const bar = this.add.rectangle(bx, by, 1, 6, 0xffc34a).setOrigin(0);
    this.load.on('progress', v => { bar.width = Math.max(1, bw * v); });

    this.load.json('manifest', 'art/pixel/manifest.json');
    for (const c of GAME.CHARACTERS) {
      this.load.image(GAME.portraitKey(c), 'art/pixel/portraits/' + c.folder + '.png');
    }

    for (const w of GAME.WORLDS) {
      const d = w.art + '/';
      this.load.json(w.id + '-meta', d + 'world.json');
      this.load.text(w.id + '-level', w.level);
      this.load.image(w.id + '-far', d + 'far.png');
      this.load.image(w.id + '-mid', d + 'mid.png');
      this.load.spritesheet(w.id + '-tiles', d + 'tiles.png', { frameWidth: 16, frameHeight: 16 });
      this.load.image(w.id + '-keyhole', d + 'keyhole.png');
      // Enemy and friend sheets load in create(), once sprites.json has told
      // us their frame sizes.
      this.load.json(w.id + '-sprites', d + 'sprites.json');
    }

    // Shared sprites.
    const d = 'art/world/pride/';
    this.load.spritesheet('heart', d + 'heart.png', { frameWidth: 11, frameHeight: 10 });
    this.load.image('keyblade', d + 'keyblade.png');
    this.load.image('swoosh', d + 'swoosh.png');
    this.load.image('munny', d + 'munny.png');
    this.load.image('heart-small', d + 'heart_small.png');
    this.load.image('sparkle', d + 'sparkle.png');
    this.load.image('hitstar', d + 'hitstar.png');
  }

  create() {
    const manifest = this.cache.json.get('manifest');
    if (!manifest) { this.fail('Could not read art/pixel/manifest.json'); return; }

    const missing = [];
    for (const c of GAME.CHARACTERS) {
      const m = manifest[c.folder];
      if (!m) { missing.push(c.folder); continue; }
      c.cell = m.cell; c.anchor = m.anchor; c.figure = m.figure; c.hand = m.hand;
      c.frames = m.animations;
      c.portrait = m.portrait;
      c.generatedAttack = !!m.generatedAttack;
      c.bladeTip = m.bladeTip;
      c.attackReach = m.attackReach || 42;
    }
    if (missing.length) { this.fail('Not in manifest: ' + missing.join(', ')); return; }

    // World art whose sizes world.json describes (generated or procedural).
    for (const w of GAME.WORLDS) {
      const meta = this.cache.json.get(w.id + '-meta') || {};
      const d = w.art + '/';
      if (meta.trees) meta.trees.forEach((_, i) => this.load.image(w.id + '-tree-' + i, d + 'tree_' + i + '.png'));
      else this.load.image(w.id + '-tree-0', d + 'acacia.png');
      if (meta.platform) {
        this.load.spritesheet(w.id + '-platform', d + 'platform.png',
          { frameWidth: meta.platform.frame[0], frameHeight: meta.platform.frame[1] });
      }
      if (meta.mover) this.load.image(w.id + '-mover', d + 'mover.png');
      if (meta.crumble) this.load.image(w.id + '-crumble', d + 'crumble.png');
      if (meta.beat) {
        this.load.spritesheet(w.id + '-beat', d + 'beat.png',
          { frameWidth: meta.beat.frame[0], frameHeight: meta.beat.frame[1] });
      }
      if (meta.bounce) this.load.image(w.id + '-bounce', d + 'bounce.png');
      if (meta.stage) this.load.image(w.id + '-stage', d + 'stage.png');
      if (meta.tileset && meta.tileset.fringe) this.load.image(w.id + '-fringe', d + 'grass_fringe.png');
      const sf = (meta.savepoint && meta.savepoint.frame) || [40, 12];
      this.load.spritesheet(w.id + '-savepoint', d + 'savepoint.png', { frameWidth: sf[0], frameHeight: sf[1] });
    }

    // Shared props, built with the Pride Lands.
    const props = this.cache.json.get(GAME.WORLDS[0].id + '-meta') || {};
    const pd = GAME.WORLDS[0].art + '/';
    if (props.chest) {
      this.load.spritesheet('chest', pd + 'chest.png',
        { frameWidth: props.chest.frame[0], frameHeight: props.chest.frame[1] });
    }
    if (props.gem) this.load.image('gem', pd + 'gem.png');

    // Every world's enemies and friend in one registry, keyed by name (the
    // Shadow is shared: the first world to list a name provides it).
    GAME.SPRITES = {};
    for (const w of GAME.WORLDS) {
      const sprites = this.cache.json.get(w.id + '-sprites') || {};
      for (const [key, meta] of Object.entries(sprites)) {
        if (GAME.SPRITES[key]) continue;
        GAME.SPRITES[key] = meta;
        this.load.spritesheet(key, w.art + '/' + (meta.file || key + '.png'),
          { frameWidth: meta.frame[0], frameHeight: meta.frame[1] });
      }
    }

    // Character sheets are tiny; load them all now, in a second pass, because
    // their frame size comes from the manifest we just read.
    for (const c of GAME.CHARACTERS) {
      const [cw, ch] = c.cell;
      for (const anim of Object.keys(c.anims)) {
        this.load.spritesheet(GAME.sheetKey(c, anim),
          'art/pixel/' + c.folder + '/' + anim + '.png', { frameWidth: cw, frameHeight: ch });
      }
    }
    this.load.once('complete', () => this.scene.start('select'));
    this.load.start();
  }

  fail(msg) {
    GAME.text(this, 20, GAME.WORLD.height / 2 + 20, msg, 8, '#ff7a7a');
    console.error(msg);
  }
};
