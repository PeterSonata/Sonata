/**
 * Sonata Bridge
 *
 * A small Node.js service that sits between Sonata (in the browser) and
 * the upstream services on the NAS / internet. Its jobs:
 *
 *   1. Proxy Jellyfin calls so the API key lives on the NAS, not in the browser
 *   2. Proxy fanart.tv lookups (working around their broken CORS headers)
 *   3. Proxy MusicBrainz lookups (so we can use a proper User-Agent and
 *      enforce a single 1/sec rate limit across all clients)
 *   4. Cache fanart.tv and MusicBrainz responses for a day
 *   5. Expose a /health endpoint for monitoring
 *
 * It does NOT terminate HTTPS itself — DSM's reverse proxy does that.
 * The bridge speaks plain HTTP on its internal port. Only the reverse
 * proxy talks to the outside world.
 *
 * Configuration comes from .env in the same directory.
 */

const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const fetch = require('node-fetch');
require('dotenv').config();

// ─── Configuration ────────────────────────────────────────────────────────────

const JELLYFIN_URL    = process.env.JELLYFIN_URL    || 'http://192.168.1.83:8096';
const JELLYFIN_API_KEY = process.env.JELLYFIN_API_KEY;
const FANART_API_KEY  = process.env.FANART_API_KEY;
const BRIDGE_PORT     = parseInt(process.env.BRIDGE_PORT || '8443', 10);

if (!JELLYFIN_API_KEY) {
  console.error('FATAL: JELLYFIN_API_KEY missing from .env');
  process.exit(1);
}
if (!FANART_API_KEY) {
  console.warn('WARNING: FANART_API_KEY missing from .env — artist photos will not work');
}

const app = express();

// Allow any origin — we don't need to lock this down because the bridge is
// reached only through DSM's reverse proxy on a domain you control.
app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Emby-Authorization, X-Emby-Token');
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  next();
});

// ─── Health check ─────────────────────────────────────────────────────────────

app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    jellyfin: JELLYFIN_URL,
    fanart_configured: !!FANART_API_KEY,
    uptime_seconds: Math.round(process.uptime()),
  });
});

// ─── Jellyfin proxy ───────────────────────────────────────────────────────────
//
// Anything under /jellyfin/* is forwarded to Jellyfin with the API key
// attached automatically. The browser never sees the key.

app.use('/jellyfin', createProxyMiddleware({
  target: JELLYFIN_URL,
  changeOrigin: true,
  pathRewrite: { '^/jellyfin': '' },
  on: {
    proxyReq: (proxyReq, req) => {
      // Attach the API key as a header (works for fetch/XHR)
      proxyReq.setHeader('X-Emby-Token', JELLYFIN_API_KEY);
      // ALSO attach as query string so <img> and <audio> tags work
      // (those can't set custom headers but Jellyfin accepts api_key in URL)
      const path = proxyReq.path;
      if (!/[?&]api_key=/.test(path)) {
        const sep = path.includes('?') ? '&' : '?';
        proxyReq.path = path + sep + 'api_key=' + encodeURIComponent(JELLYFIN_API_KEY);
      }
    },
    proxyRes: (proxyRes, req, res) => {
      // Strip set-cookie since we don't use sessions
      delete proxyRes.headers['set-cookie'];
      // FORCE CORS headers on every proxied response, overriding any from
      // upstream and ensuring they're set before streaming begins.
      // This is critical for large responses (e.g. the full library fetch)
      // where headers set earlier in middleware can get lost.
      proxyRes.headers['access-control-allow-origin']  = '*';
      proxyRes.headers['access-control-allow-methods'] = 'GET, POST, PUT, DELETE, OPTIONS';
      proxyRes.headers['access-control-allow-headers'] = 'Content-Type, Authorization, X-Emby-Authorization, X-Emby-Token';
      proxyRes.headers['access-control-expose-headers'] = '*';
    },
    error: (err, req, res) => {
      console.error(`[jellyfin] proxy error for ${req.url}:`, err.message);
      if (!res.headersSent) {
        res.setHeader('Access-Control-Allow-Origin', '*');
        res.status(502).json({ error: 'Upstream Jellyfin error', detail: err.message });
      }
    },
  },
}));

// ─── fanart.tv proxy with caching ─────────────────────────────────────────────
//
// /fanart/:mbid -> webservice.fanart.tv/v3/music/:mbid?api_key=...
// Caches successful responses for 24 hours.

const fanartCache = new Map(); // mbid -> { data, expires }
const FANART_CACHE_MS = 24 * 60 * 60 * 1000;

app.get('/fanart/:mbid', async (req, res) => {
  const { mbid } = req.params;
  if (!FANART_API_KEY) {
    return res.status(503).json({ error: 'fanart.tv not configured' });
  }
  if (!/^[0-9a-f-]{30,40}$/i.test(mbid)) {
    return res.status(400).json({ error: 'Invalid MBID format' });
  }

  // Cache hit
  const cached = fanartCache.get(mbid);
  if (cached && cached.expires > Date.now()) {
    return res.json(cached.data);
  }

  try {
    const url = `https://webservice.fanart.tv/v3/music/${mbid}?api_key=${FANART_API_KEY}`;
    const r = await fetch(url, { timeout: 8000 });
    if (r.status === 404) {
      // Cache the miss too, so we don't keep hitting fanart for known-empty MBIDs
      const empty = { artistthumb: [], artistbackground: [] };
      fanartCache.set(mbid, { data: empty, expires: Date.now() + FANART_CACHE_MS });
      return res.json(empty);
    }
    if (!r.ok) {
      console.warn(`[fanart] ${r.status} for ${mbid}`);
      return res.status(r.status).json({ error: `fanart.tv returned ${r.status}` });
    }
    const data = await r.json();
    fanartCache.set(mbid, { data, expires: Date.now() + FANART_CACHE_MS });
    res.json(data);
  } catch (e) {
    console.error(`[fanart] error for ${mbid}:`, e.message);
    res.status(502).json({ error: 'fanart.tv upstream error', detail: e.message });
  }
});

// ─── MusicBrainz proxy with caching and rate limiting ─────────────────────────
//
// /mbid?artist=NAME -> musicbrainz.org/ws/2/artist/?query=NAME
// Caches results for 24 hours. Enforces 1 request per second across all
// clients (a hard MusicBrainz rule that we previously violated by allowing
// each browser to call directly).

const mbidCache = new Map();        // artistName -> { mbid, expires }
const MBID_CACHE_MS = 24 * 60 * 60 * 1000;

let mbidQueue = Promise.resolve();
function rateLimitedFetch(url) {
  // Chain each call onto the previous one with a 1.1-second gap.
  // This serialises every MB request system-wide.
  const wait = mbidQueue.then(() => new Promise(r => setTimeout(r, 1100)));
  mbidQueue = wait;
  return wait.then(() => fetch(url, {
    headers: { 'User-Agent': 'Sonata-Bridge/1.0 (personal music player)' },
    timeout: 10000,
  }));
}

app.get('/mbid', async (req, res) => {
  const artist = (req.query.artist || '').trim();
  if (!artist) return res.status(400).json({ error: 'artist parameter required' });

  // Cache hit
  const cached = mbidCache.get(artist);
  if (cached && cached.expires > Date.now()) {
    return res.json({ mbid: cached.mbid, cached: true });
  }

  // Strip Lucene specials and use unquoted query for fuzzy matching
  const clean = artist.replace(/[+\-!(){}\[\]^"~*?:\\\/]/g, ' ').replace(/\s+/g, ' ').trim();
  if (!clean) {
    mbidCache.set(artist, { mbid: null, expires: Date.now() + MBID_CACHE_MS });
    return res.json({ mbid: null });
  }

  try {
    const url = `https://musicbrainz.org/ws/2/artist/?query=${encodeURIComponent(clean)}&limit=1&fmt=json`;
    const r = await rateLimitedFetch(url);
    if (r.status >= 500 || r.status === 429) {
      // Transient — don't cache, surface the error
      console.warn(`[mbid] transient ${r.status} for "${artist}"`);
      return res.status(r.status).json({ error: `MusicBrainz returned ${r.status}` });
    }
    if (!r.ok) {
      // Definitive error — cache as null so we don't retry uselessly
      mbidCache.set(artist, { mbid: null, expires: Date.now() + MBID_CACHE_MS });
      return res.json({ mbid: null });
    }
    const data = await r.json();
    const mbid = data.artists?.[0]?.id || null;
    mbidCache.set(artist, { mbid, expires: Date.now() + MBID_CACHE_MS });
    res.json({ mbid });
  } catch (e) {
    console.error(`[mbid] error for "${artist}":`, e.message);
    res.status(502).json({ error: 'MusicBrainz upstream error', detail: e.message });
  }
});

// ─── Cache stats (handy for debugging) ────────────────────────────────────────

app.get('/stats', (req, res) => {
  res.json({
    fanart_cache_size: fanartCache.size,
    mbid_cache_size: mbidCache.size,
    uptime_seconds: Math.round(process.uptime()),
    memory_mb: Math.round(process.memoryUsage().heapUsed / 1024 / 1024),
  });
});

// ─── Start server ─────────────────────────────────────────────────────────────

app.listen(BRIDGE_PORT, () => {
  console.log(`Sonata Bridge listening on port ${BRIDGE_PORT}`);
  console.log(`  Jellyfin: ${JELLYFIN_URL}`);
  console.log(`  fanart.tv: ${FANART_API_KEY ? 'configured' : 'NOT configured'}`);
  console.log(`  Endpoints: /health, /jellyfin/*, /fanart/:mbid, /mbid?artist=NAME, /stats`);
});

// Graceful shutdown
process.on('SIGINT',  () => { console.log('Shutting down…'); process.exit(0); });
process.on('SIGTERM', () => { console.log('Shutting down…'); process.exit(0); });
