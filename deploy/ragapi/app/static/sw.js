const CACHE_NAME = 'v1';
const FILES_TO_CACHE = [
  '/pwa/manifest.json',
  '/pwa/webchat.html',
  '/pwa/webchat.js',
  '/pwa/sw.js',
  '/pwa/icon-192x192.png',
  '/pwa/icon-512x512.png'
];

// 🏗 Instala y precachea recursos
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      console.log('Precaching archivos:', FILES_TO_CACHE);
      return cache.addAll(FILES_TO_CACHE);
    })
  );
  self.skipWaiting(); // Activa inmediatamente
});

// 🌐 Sirve desde cache si está disponible
self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request).then(response => {
      return response || fetch(event.request);
    })
  );
});

// 🔔 Maneja notificaciones push
self.addEventListener('push', (event) => {
  let data = { title: 'Real[IA]', body: 'Tienes una nueva notificación' };

  if (event.data) {
    try {
      data = event.data.json();
    } catch (error) {
      console.warn("No se pudo parsear como JSON. Usando texto plano.");
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body.length > 120 ? data.body.substring(0, 117) + '...' : data.body,
    icon: '/icons/icon-192x192.png',
    badge: '/icons/icon-96x96.png',
    tag: 'realia',
    renotify: true,
    actions: [
        { action: 'leer', title: 'Leer mensaje' },
        { action: 'responder', title: 'Responder' }
      ]
  };

  event.waitUntil(
    self.registration.showNotification(data.title || "Nuevo mensaje", options)
  );
});
