/* ---------------------------------------------------------------------------
 * Little visual effects. Tween-driven pixel sprites rather than a particle
 * system: there are never more than a few dozen on screen, and each one stays
 * on whole pixels.
 * ------------------------------------------------------------------------- */
window.GAME = window.GAME || {};

GAME.Fx = class Fx {
  constructor(scene) { this.scene = scene; }

  sparkles(x, y, tint, n) {
    const sc = this.scene;
    for (let i = 0; i < (n || 8); i++) {
      const a = Math.random() * Math.PI * 2, r = 10 + Math.random() * 18;
      const p = sc.add.image(x, y, 'sparkle').setDepth(20).setTint(tint || 0xffffff);
      sc.tweens.add({
        targets: p, x: x + Math.cos(a) * r, y: y + Math.sin(a) * r - 6, alpha: 0,
        duration: 380 + Math.random() * 260, ease: 'Quad.easeOut', onComplete: () => p.destroy(),
      });
    }
  }

  rise(x, y, tint) {
    const sc = this.scene;
    const p = sc.add.image(x + (Math.random() - 0.5) * 20, y, 'sparkle').setDepth(6).setTint(tint).setAlpha(0.9);
    sc.tweens.add({ targets: p, y: y - 40 - Math.random() * 20, alpha: 0, duration: 1100, onComplete: () => p.destroy() });
  }

  hit(x, y) {
    const sc = this.scene;
    const s = sc.add.image(x, y, 'hitstar').setDepth(21).setScale(1);
    sc.tweens.add({ targets: s, scale: 2, alpha: 0, angle: 45, duration: 220, onComplete: () => s.destroy() });
    this.sparkles(x, y, 0xffffff, 6);
  }

  /** What a defeated Heartless leaves behind: a heart, floating up and away. */
  heartRelease(x, y) {
    const sc = this.scene;
    const h = sc.add.image(x, y, 'heart-small').setDepth(21);
    sc.tweens.add({ targets: h, y: y - 46, duration: 1000, ease: 'Sine.easeOut' });
    sc.tweens.add({ targets: h, x: x + 6, duration: 250, yoyo: true, repeat: 3, ease: 'Sine.easeInOut' });
    sc.tweens.add({ targets: h, alpha: 0, delay: 600, duration: 400, onComplete: () => h.destroy() });
  }

  say(x, y, str) {
    const sc = this.scene;
    const t = GAME.text(sc, x, y, str, 8, '#fff3d0').setOrigin(0.5, 1).setDepth(30)
      .setStroke('#3a1a3a', 3);
    sc.tweens.add({ targets: t, y: y - 10, duration: 900, ease: 'Quad.easeOut' });
    sc.tweens.add({ targets: t, alpha: 0, delay: 650, duration: 300, onComplete: () => t.destroy() });
  }
};
