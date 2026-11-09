/* ---------------------------------------------------------------------------
 * Boot. Pinned to Phaser 3.90.0 (see the script tag in index.html).
 * ------------------------------------------------------------------------- */
window.GAME = window.GAME || {};

GAME.start = function () {
  if (GAME.game) return;
  GAME.game = new Phaser.Game({
    type: Phaser.AUTO,
    parent: 'game',
    backgroundColor: '#120a1e',

    // 640x360 is the pixel-art screen; FIT blows it up to the phone with
    // nearest-neighbour sampling, and roundPixels keeps every sprite on whole
    // pixels so nothing shimmers while the camera scrolls.
    width: GAME.WORLD.width,
    height: GAME.WORLD.height,
    pixelArt: true,
    roundPixels: true,
    scale: {
      mode: Phaser.Scale.FIT,
      autoCenter: Phaser.Scale.CENTER_BOTH,
      width: GAME.WORLD.width,
      height: GAME.WORLD.height,
    },

    // Four touch points: holding right while tapping jump needs two.
    input: { activePointers: 4, touch: { capture: true } },

    physics: {
      default: 'arcade',
      arcade: { gravity: { y: GAME.WORLD.gravity }, debug: false },
    },

    scene: [GAME.PreloadScene, GAME.SelectScene, GAME.WorldScene, GAME.PlayScene],
  });
};

// Wait for the pixel font, or the first frame of text renders in a fallback
// face and never repaints. Give up after 2.5s so a missing network can't hang
// the game.
(function () {
  const go = () => GAME.start();
  if (document.fonts && document.fonts.load) {
    Promise.race([
      document.fonts.load('8px "Press Start 2P"'),
      new Promise(r => setTimeout(r, 2500)),
    ]).then(go, go);
  } else {
    go();
  }
})();
