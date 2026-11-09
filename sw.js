/* ---------------------------------------------------------------------------
 * Service worker: lets the home-screen app start without a connection.
 *
 * Network first: with a connection you always get the newest version of the
 * game; every file that loads is also kept in a cache, and when there's no
 * connection the cached copy is used instead. The first visit has to be
 * online (that's what fills the cache).
 * ------------------------------------------------------------------------- */
const CACHE = 'kingdom-kids-v1';

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
      const res = await fetch(req);
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
