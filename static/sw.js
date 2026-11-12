/* Service worker: ilovani telefonga o'rnatish (PWA) va statik fayllarni oflayn ushlab turish.
   API so'rovlari va boshqa domenlar (xarita bo'laklari) HECH QACHON keshlanmaydi. */
const CACHE = "solar-v1";
const PRECACHE = [
  "/static/style.css",
  "/static/i18n.js",
  "/static/common.js",
  "/static/app.js",
  "/static/icons/icon-192.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => Promise.allSettled(PRECACHE.map((url) => cache.add(url))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // xarita bo'laklari, CDN
  if (url.pathname.startsWith("/api/")) return; // har doim tarmoqdan

  // Statik fayllar: avval tarmoq (yangi bo'lishi uchun), oflayn bo'lsa — kesh
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((cache) => cache.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  // Sahifalar (foydalanuvchiga xos) keshlanmaydi: oflayn bo'lsa, qisqa xabar
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(
        () =>
          new Response(
            "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>" +
              "<body style='font-family:sans-serif;padding:2rem'><h2>Offline</h2>" +
              "<p>Internet aloqasi yo'q. Tahlil uchun server bilan aloqa kerak.</p></body>",
            { headers: { "Content-Type": "text/html; charset=utf-8" } }
          )
      )
    );
  }
});
