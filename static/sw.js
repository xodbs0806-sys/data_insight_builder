const CACHE_NAME = 'data-insight-builder-v1';
const STATIC_ASSETS = [
    '/static/style.css',
    '/static/app.js',
    '/static/manifest.json',
    '/static/icons/icon-192.png',
    '/static/icons/icon-512.png',
    '/static/icons/apple-touch-icon.png'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS);
        }).then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
            );
        }).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // API 요청 및 인증 요청은 항상 네트워크로 직접 요청
    if (
        url.pathname.startsWith('/inspect') ||
        url.pathname.startsWith('/suggest') ||
        url.pathname.startsWith('/run') ||
        url.pathname.startsWith('/explain') ||
        url.pathname.startsWith('/ask') ||
        url.pathname.startsWith('/login') ||
        url.pathname.startsWith('/logout') ||
        url.pathname.startsWith('/health') ||
        event.request.method !== 'GET'
    ) {
        return;
    }

    // 정적 자산(CSS, JS, 아이콘)은 Cache First 또는 Network Fallback
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            if (cachedResponse) {
                // 백그라운드에서 캐시 업데이트 (Stale-while-revalidate)
                fetch(event.request).then((networkResponse) => {
                    if (networkResponse && networkResponse.status === 200) {
                        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, networkResponse));
                    }
                }).catch(() => {});
                return cachedResponse;
            }
            return fetch(event.request);
        })
    );
});
