/**
 * LamboTaxi — API Adapter
 * Reemplaza localStorage con llamadas al servidor.
 * Incluir este script ANTES del script principal de lt.html
 *
 * Uso: <script src="/static/api-adapter.js"></script>
 *       <script> // código de lt.html </script>
 */

(function () {
  'use strict';

  const API_BASE = window.location.origin;
  const TOKEN_KEY = 'lt_token';

  // ── Get auth token ──────────────────────────────────────────────────────
  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  // ── Check auth on load ──────────────────────────────────────────────────
  async function checkAuth() {
    const token = getToken();
    if (!token) {
      window.location.href = '/';
      return false;
    }
    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        headers: { Authorization: 'Bearer ' + token }
      });
      if (!res.ok) { window.location.href = '/'; return false; }
      const user = await res.json();
      // Store user info for the app
      window.__LT_USER = user;
      return true;
    } catch {
      window.location.href = '/';
      return false;
    }
  }

  // ── Remote storage (replaces localStorage for lt_ keys) ─────────────────
  const pendingSync = {};
  let syncTimer = null;

  async function remoteGet(key) {
    const token = getToken();
    if (!token) return null;
    try {
      const res = await fetch(`${API_BASE}/api/data/${encodeURIComponent(key)}`, {
        headers: { Authorization: 'Bearer ' + token }
      });
      if (!res.ok) return null;
      const data = await res.json();
      return data.value;
    } catch {
      return null;
    }
  }

  async function remoteSet(key, value) {
    const token = getToken();
    if (!token) return;
    // Debounce — batch writes every 2 seconds
    pendingSync[key] = value;
    clearTimeout(syncTimer);
    syncTimer = setTimeout(flushSync, 2000);
  }

  async function flushSync() {
    const token = getToken();
    if (!token || !Object.keys(pendingSync).length) return;
    const batch = { ...pendingSync };
    Object.keys(batch).forEach(k => delete pendingSync[k]);
    try {
      await fetch(`${API_BASE}/api/data`, {
        method: 'POST',
        headers: {
          Authorization: 'Bearer ' + token,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(batch)
      });
    } catch {
      // Restore pending on failure
      Object.assign(pendingSync, batch);
    }
  }

  // ── Intercept localStorage for LamboTaxi keys ───────────────────────────
  // LamboTaxi uses keys like: lt_tx, lt_fuel, lt_sets, lt_gestoria, etc.
  const LT_KEY_PREFIX = 'lt_';
  const _origGetItem = Storage.prototype.getItem;
  const _origSetItem = Storage.prototype.setItem;

  // Keep a local cache so the app doesn't have to await every read
  const _cache = {};
  let _loaded = false;

  // Override getItem: return from cache
  Storage.prototype.getItem = function (key) {
    if (key.startsWith(LT_KEY_PREFIX) && _loaded) {
      return _cache.hasOwnProperty(key) ? _cache[key] : null;
    }
    return _origGetItem.call(this, key);
  };

  // Override setItem: update cache + queue remote write
  Storage.prototype.setItem = function (key, value) {
    if (key.startsWith(LT_KEY_PREFIX) && _loaded) {
      _cache[key] = value;
      remoteSet(key, JSON.parse(value));
    }
    return _origSetItem.call(this, key, value);
  };

  // ── Load all user data at startup ────────────────────────────────────────
  async function loadAllData() {
    const token = getToken();
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/api/data`, {
        headers: { Authorization: 'Bearer ' + token }
      });
      if (!res.ok) return;
      const data = await res.json();
      // Populate cache with server data
      Object.entries(data).forEach(([key, value]) => {
        const storageKey = key.startsWith(LT_KEY_PREFIX) ? key : LT_KEY_PREFIX + key;
        _cache[storageKey] = JSON.stringify(value);
        // Also write to real localStorage as fallback
        _origSetItem.call(localStorage, storageKey, JSON.stringify(value));
      });
      _loaded = true;
      console.log(`✅ LamboTaxi: ${Object.keys(data).length} claves cargadas del servidor`);
    } catch (e) {
      console.warn('⚠️ LamboTaxi: no se pudo cargar datos del servidor, usando localStorage local', e);
      _loaded = true; // Fall back to localStorage
    }
  }

  // ── Export to server button (in settings) ───────────────────────────────
  window.__LT_EXPORT_TO_SERVER = async function () {
    const token = getToken();
    if (!token) return alert('No autenticado');
    const allData = {};
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith(LT_KEY_PREFIX)) {
        try { allData[key] = JSON.parse(localStorage.getItem(key)); } catch { }
      }
    }
    const res = await fetch(`${API_BASE}/api/data`, {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify(allData)
    });
    if (res.ok) alert('✅ Datos exportados al servidor correctamente');
    else alert('❌ Error al exportar');
  };

  // ── Logout helper ────────────────────────────────────────────────────────
  window.__LT_LOGOUT = function () {
    flushSync(); // Make sure pending writes go through
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem('lt_user');
    window.location.href = '/';
  };

  // ── Bootstrap ────────────────────────────────────────────────────────────
  window.__LT_API_READY = (async function () {
    const authed = await checkAuth();
    if (!authed) return;
    await loadAllData();
    // Flush any pending writes before the page unloads
    window.addEventListener('beforeunload', flushSync);
    console.log(`✅ LamboTaxi API adapter listo — usuario: ${window.__LT_USER?.email}`);
  })();

})();
