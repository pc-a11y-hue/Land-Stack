/* Land Stack service worker.
   - App shell (HTML/JS/icons) and Leaflet assets: cached so the app opens offline.
   - /api/*: NEVER cached (land records and OTPs are sensitive) — offline gives a clear message.
   - Map tiles: never cached (tile-server usage policies forbid bulk caching). */
const VERSION = 'landstack-v1';
const SHELL = ['/', '/citizen', '/officer', '/app.js', '/i18n.js', '/manifest.webmanifest',
               '/icons/icon-192.png', '/icons/icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  if (url.origin === location.origin && url.pathname.startsWith('/api/')) {
    e.respondWith(fetch(req).catch(() => new Response(
      JSON.stringify({ error: 'You are offline. Land records are only available online.' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } })));
    return;
  }
  if (url.hostname.endsWith('tile.openstreetmap.org') || url.pathname.includes('/tiles/')) return;   // tiles: network only

  if (url.origin === location.origin || url.hostname === 'unpkg.com') {
    // network-first with cache fallback, so updates are picked up but offline still works
    e.respondWith(fetch(req).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(VERSION).then(c => c.put(req, copy)); }
      return res;
    }).catch(() => caches.match(req).then(hit => hit || (req.mode === 'navigate' ? caches.match('/') : Response.error()))));
  }
});
