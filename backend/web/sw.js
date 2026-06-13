const CACHE = "echo-v1";
const ASSETS = ["/", "/index.html", "/styles.css", "/app.js", "/manifest.webmanifest"];
self.addEventListener("install", (e) =>
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS))));
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) return; // always network for API
  e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
});
