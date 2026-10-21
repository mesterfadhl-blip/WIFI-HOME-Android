const CACHE = 'wifi-home-web-v1';
const FILES = ['./', './index.html', './manifest.webmanifest', './icons/icon.svg'];
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(FILES))); });
self.addEventListener('activate', event => { event.waitUntil(self.clients.claim()); });
self.addEventListener('fetch', event => {
 if (event.request.method !== 'GET' || new URL(event.request.url).origin !== self.location.origin) return;
 event.respondWith(fetch(event.request).catch(() => caches.match(event.request).then(response => response || (event.request.mode === 'navigate' ? caches.match('./index.html') : Response.error()))));
});
