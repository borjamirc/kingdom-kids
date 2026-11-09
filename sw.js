/* ---------------------------------------------------------------------------
 * Service worker: lets the home-screen app start without a connection.
 *
 * Network first: with a connection you always get the newest version of the
 * game; every file that loads is also kept in a cache, and when there's no
 * connection the cached copy is used instead. The first visit has to be
 * online (that's what fills the cache).
 *
 * The game's own files are always re-checked with the server ('no-cache'):
 * GitHub Pages lets browsers reuse a file for 10 minutes without asking, so
 * right after an update a phone could mix new files with old ones (a new
 * play screen calling a helper an old characters.js doesn't have). A re-check
 * that finds nothing new costs one tiny 304 reply.
 * ------------------------------------------------------------------------- */
const CACHE = 'kingdom-kids-v2';

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) if (key !== CACHE) await caches.delete(key);
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    try {
      const own = new URL(req.url).origin === self.location.origin;
      const res = await fetch(own ? new Request(req.url, { cache: 'no-cache' }) : req);
      // ok responses, plus opaque ones from the font CDN (no-cors)
      if (res.ok || res.type === 'opaque') cache.put(req, res.clone());
      return res;
    } catch (err) {
      const hit = await cache.match(req, { ignoreSearch: true });
      if (hit) return hit;
      throw err;
    }
  })());
});
