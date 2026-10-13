/**
 * LamboTaxi — Service Worker
 * Versión: 1.0.0
 * Estrategia: Cache-first para assets estáticos, Network-first para API
 */

const CACHE_NAME = 'lambotaxi-v1';
const CACHE_STATIC = 'lambotaxi-static-v1';
const CACHE_API    = 'lambotaxi-api-v1';

// Archivos que se cachean en la instalación
const STATIC_ASSETS = [
  '/app',
  '/conductor',
  '/static/api-adapter.js',
  'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js',
  'https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/jspdf-autotable/3.8.2/jspdf.plugin.autotable.min.js',
];

// ── Install ──────────────────────────────────────────────────────────────────
self.addEventListener('install', event => {
  console.log('[SW] Instalando LamboTaxi v1');
  event.waitUntil(
    caches.open(CACHE_STATIC)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
      .catch(err => console.warn('[SW] Error en precache:', err))
  );
});

// ── Activate ─────────────────────────────────────────────────────────────────
self.addEventListener('activate', event => {
  console.log('[SW] Activado');
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== CACHE_STATIC && k !== CACHE_API)
            .map(k => { console.log('[SW] Eliminando caché antigua:', k); return caches.delete(k); })
      )
    ).then(() => self.clients.claim())
  );
});

// ── Fetch ─────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // No interceptar: auth, admin, peticiones externas de no-CDN
  if (url.pathname.startsWith('/auth/') ||
      url.pathname.startsWith('/admin/') ||
      (url.origin !== location.origin && !url.hostname.includes('cdnjs'))) {
    return;
  }

  // API calls: Network-first, fallback a caché
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/jornada')) {
    event.respondWith(networkFirst(event.request));
    return;
  }

  // Assets estáticos (CDN incluidos): Cache-first
  if (url.pathname.includes('.js') || url.pathname.includes('.css') ||
      url.hostname.includes('cdnjs')) {
    event.respondWith(cacheFirst(event.request));
    return;
  }

  // Páginas HTML: Network-first con fallback offline
  if (event.request.mode === 'navigate' ||
      event.request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(networkFirstWithOfflineFallback(event.request));
    return;
  }

  // Default: network-first
  event.respondWith(networkFirst(event.request));
});

// ── Strategies ────────────────────────────────────────────────────────────────
async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_STATIC);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response('Recurso no disponible offline', { status: 503 });
  }
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok && request.method === 'GET') {
      const cache = await caches.open(CACHE_API);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached || new Response(JSON.stringify({ error: 'Sin conexión' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

async function networkFirstWithOfflineFallback(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_STATIC);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request) ||
                   await caches.match('/app');
    return cached || offlinePage();
  }
}

function offlinePage() {
  return new Response(`<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LamboTaxi — Sin conexión</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,sans-serif;background:#f2f2f7;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;padding:24px;text-align:center}
.icon{font-size:64px;margin-bottom:20px}.title{font-size:22px;font-weight:700;margin-bottom:8px}.sub{font-size:14px;color:#8e8e93;margin-bottom:24px}
.btn{padding:12px 28px;border-radius:20px;background:#007aff;color:#fff;border:none;font-size:15px;font-weight:500;cursor:pointer}</style></head>
<body><div class="icon">📡</div><div class="title">Sin conexión</div>
<div class="sub">LamboTaxi necesita conexión para cargar.<br>Los datos guardados localmente siguen disponibles.</div>
<button class="btn" onclick="location.reload()">Reintentar</button></body></html>`,
    { headers: { 'Content-Type': 'text/html' } });
}

// ── Push notifications ────────────────────────────────────────────────────────
self.addEventListener('push', event => {
  const data = event.data?.json() || {};
  event.waitUntil(
    self.registration.showNotification(data.title || 'LamboTaxi', {
      body: data.body || '',
      icon: '/static/icon-192.png',
      badge: '/static/icon-72.png',
      data: { url: data.url || '/app' }
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    clients.openWindow(event.notification.data?.url || '/app')
  );
});
