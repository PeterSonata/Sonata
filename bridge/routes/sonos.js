// routes/sonos.js
// ============================================================
// Sonos control endpoints for the bridge.
//
// Read endpoints (open):
//   GET  /sonos                 list discovered + configured players
//
// Control endpoints (require X-Sonata-Key from outside the LAN;
// requests from a private/LAN address skip the key, since casting
// only works on the local network anyway):
//   POST /sonos/play            body { host, uris: [...] } | { host, uri }
//   POST /sonos/pause           body { host }
//   POST /sonos/resume          body { host }
//   POST /sonos/next            body { host }            (manual skip)
//   POST /sonos/previous        body { host }
//   POST /sonos/volume          body { host, level }     (0..100)
//
// Queue model: push-on-advance. The desktop client sends the whole
// list of track URLs once. The bridge plays the first, holds the
// rest in the store keyed by host, and a polling job advances to
// the next track when the player reports STOPPED. This mirrors the
// iOS background-advance thinking rather than loading a native
// Sonos queue, which keeps the SOAP surface to set-uri + play.
//
// The track URLs must be LAN-reachable Jellyfin stream URLs. The
// speaker streams straight from the NAS, so do NOT hand it the
// external DuckDNS address: that would hairpin out and back. The
// client is responsible for building the local URL; the bridge
// just relays it.
// ============================================================

const express = require('express');
const router = express.Router();

const sonos = require('../lib/sonos');
const auth = require('../lib/auth');
const store = require('../lib/store');

// LAN-aware auth for the control routes. Sonos only does anything
// useful when the caller is on the same network as the speakers and
// the NAS, so a request from a private address is trusted and skips
// the X-Sonata-Key check. Anything arriving from outside (e.g. via
// the external DuckDNS forward) still goes through the normal auth
// guard, so the public surface is not left open.
//
// Private ranges: 10/8, 172.16/12, 192.168/16, plus loopback and
// IPv4-mapped IPv6 (::ffff:192.168.x.x), which is how Node reports
// LAN clients when the socket is dual-stack.
function isPrivateAddr(ip) {
  if (!ip) return false;
  // Strip IPv4-mapped IPv6 prefix.
  const addr = ip.replace(/^::ffff:/, '');
  if (addr === '127.0.0.1' || addr === '::1') return true;
  if (addr.startsWith('10.')) return true;
  if (addr.startsWith('192.168.')) return true;
  // 172.16.0.0 - 172.31.255.255
  const m = addr.match(/^172\.(\d+)\./);
  if (m) {
    const second = parseInt(m[1], 10);
    if (second >= 16 && second <= 31) return true;
  }
  return false;
}

function lanOrAuth(req, res, nextMw) {
  // req.ip respects trust proxy if set; fall back to the raw socket.
  const ip = req.ip || (req.socket && req.socket.remoteAddress) || '';
  if (isPrivateAddr(ip)) return nextMw();
  return auth(req, res, nextMw);
}

// How often the advance poller checks each active player, in ms.
// Sonos transport state is cheap to read and 4s is responsive
// enough for gapless-ish advance without hammering the speaker.
const POLL_MS = 4000;

// Store key holding per-host queue state:
//   { [host]: { remaining: [uri, ...], current: uri|null } }
const QUEUE_KEY = 'sonosQueues';

async function readQueues() {
  try {
    const v = await store.get(QUEUE_KEY);
    return v || {};
  } catch (_) {
    return {};
  }
}

async function writeQueue(host, entry) {
  await store.update(QUEUE_KEY, (queues) => {
    const next = { ...(queues || {}) };
    if (entry === null) {
      delete next[host];
    } else {
      next[host] = entry;
    }
    return next;
  });
}

// ------------------------------------------------------------
// Read: list players
// ------------------------------------------------------------
router.get('/sonos', async (req, res) => {
  try {
    // Find the speakers on the LAN (plus any configured fallbacks).
    const players = await sonos.discover(3000);

    // Ask any one of them for the household topology. All players share
    // it, so a single call collapses stereo pairs and bonded units to one
    // addressable entry per room (the group coordinator). Querying from a
    // satellite is fine: it still serves the full topology.
    const seed = (players[0] && players[0].host) || sonos.configuredHosts()[0];
    let named = null;
    if (seed) {
      try {
        const zones = await sonos.getZones(seed);
        if (zones.length > 0) named = zones;
      } catch (_) {
        // Topology read failed; fall through to the per-host path.
      }
    }

    // Fallback: the old discover + per-host roomName listing. Degrades to a
    // duplicated-but-functional list rather than an empty picker.
    if (!named) named = await sonos.withRoomNames(players);

    res.json({
      players: named,
      configured: sonos.configuredHosts(),
      count: named.length,
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ------------------------------------------------------------
// Stream URL construction (server-side)
// ------------------------------------------------------------
// The speaker streams bytes from Jellyfin directly, so it needs a
// LAN-reachable URL. The client must NOT build this (its own path to
// the bridge may be Tailscale/QuickConnect, which the speaker cannot
// route to). The bridge knows its own LAN Jellyfin address from
// config, so it builds the URL here. Two hard-won details are baked
// in permanently: the .mp3 extension (a bare /stream gives UPnP 714,
// illegal MIME-type, because Sonos is strict about the container),
// and the API key, kept server-side rather than handed to clients.
let _cfg = null;
function jellyfinConfig() {
  if (_cfg) return _cfg;
  let base = process.env.JELLYFIN_URL || '';
  let key = process.env.JELLYFIN_API_KEY || '';
  // Fall back to lib/config if it exposes the values.
  if (!base || !key) {
    try {
      const c = require('../lib/config');
      base = base || c.JELLYFIN_URL || (c.jellyfin && c.jellyfin.url) || '';
      key = key || c.JELLYFIN_API_KEY || (c.jellyfin && c.jellyfin.apiKey) || '';
    } catch (_) { /* config shape differs; env is enough */ }
  }
  _cfg = { base: base.replace(/\/$/, ''), key };
  return _cfg;
}

// Build the LAN .mp3 stream URL for a Jellyfin item id.
function streamUrlForId(id) {
  const { base, key } = jellyfinConfig();
  if (!base) throw new Error('JELLYFIN_URL not configured on the bridge');
  const keyParam = key ? `&api_key=${encodeURIComponent(key)}` : '';
  return `${base}/Audio/${encodeURIComponent(id)}/stream.mp3?static=true${keyParam}`;
}

// ------------------------------------------------------------
// Control: play a list from the start
// ------------------------------------------------------------
// Accepts item ids (preferred) and builds LAN stream URLs itself, or
// raw uris (kept for the curl test path). ids take precedence.
router.post('/sonos/play', lanOrAuth, async (req, res) => {
  const { host, ids } = req.body || {};
  let { uris, uri } = req.body || {};
  if (!host) return res.status(400).json({ error: 'host required' });

  // Prefer ids: build the speaker URLs server-side.
  if (Array.isArray(ids) && ids.length > 0) {
    try {
      uris = ids.map(streamUrlForId);
    } catch (err) {
      return res.status(500).json({ error: err.message });
    }
  }

  if (!uris && uri) uris = [uri];
  if (!Array.isArray(uris) || uris.length === 0) {
    return res.status(400).json({ error: 'ids (array), uris (array) or uri required' });
  }

  try {
    const [first, ...rest] = uris;
    await sonos.setUri(host, first);
    await sonos.play(host);
    await writeQueue(host, { remaining: rest, current: first });
    res.json({ ok: true, playing: first, queued: rest.length });
  } catch (err) {
    res.status(502).json({ error: err.message });
  }
});

// ------------------------------------------------------------
// Read: current playback state for a host
// ------------------------------------------------------------
// The client polls this to follow the speaker: as the push-on-
// advance poller moves through the queue on natural track ends,
// the client reads currentId and points its display at the
// matching queue entry. We return the Jellyfin item id parsed out
// of the stored stream URL rather than the URL itself, so the
// embedded api_key is never exposed over the external forward.
router.get('/sonos/state', lanOrAuth, async (req, res) => {
  const host = req.query.host;
  if (!host) return res.status(400).json({ error: 'host required' });
  try {
    const queues = await readQueues();
    const entry = queues[host] || null;
    let currentId = null;
    if (entry && entry.current) {
      const m = String(entry.current).match(/\/Audio\/([^/]+)\/stream/);
      if (m) currentId = decodeURIComponent(m[1]);
    }
    let transport = null;
    try { transport = await sonos.getTransportState(host); } catch (_) {}
    res.json({
      active: !!entry,
      currentId,
      remaining: entry && entry.remaining ? entry.remaining.length : 0,
      transport,
    });
  } catch (err) {
    res.status(502).json({ error: err.message });
  }
});

// ------------------------------------------------------------
// Control: transport
// ------------------------------------------------------------
function transportRoute(path, fn) {
  router.post(path, lanOrAuth, async (req, res) => {
    const { host } = req.body || {};
    if (!host) return res.status(400).json({ error: 'host required' });
    try {
      await fn(req.body);
      res.json({ ok: true });
    } catch (err) {
      res.status(502).json({ error: err.message });
    }
  });
}

transportRoute('/sonos/pause', ({ host }) => sonos.pause(host));
transportRoute('/sonos/resume', ({ host }) => sonos.play(host));
transportRoute('/sonos/previous', ({ host }) => sonos.previous(host));

// Manual skip: advance our own queue rather than calling Sonos Next,
// since the native queue is empty (we push one URI at a time).
router.post('/sonos/next', lanOrAuth, async (req, res) => {
  const { host } = req.body || {};
  if (!host) return res.status(400).json({ error: 'host required' });
  try {
    const advanced = await advance(host);
    res.json({ ok: true, ...advanced });
  } catch (err) {
    res.status(502).json({ error: err.message });
  }
});

router.post('/sonos/volume', lanOrAuth, async (req, res) => {
  const { host, level } = req.body || {};
  if (!host) return res.status(400).json({ error: 'host required' });
  if (level === undefined) return res.status(400).json({ error: 'level required' });
  try {
    await sonos.setVolume(host, level);
    res.json({ ok: true, level });
  } catch (err) {
    res.status(502).json({ error: err.message });
  }
});

// ------------------------------------------------------------
// Advance logic, shared by manual skip and the poller
// ------------------------------------------------------------
// Pull the next URI off this host's queue and play it. If the queue
// is empty, clear the host's entry so the poller stops watching it.
async function advance(host) {
  const queues = await readQueues();
  const entry = queues[host];
  if (!entry || !entry.remaining || entry.remaining.length === 0) {
    await writeQueue(host, null);
    return { done: true };
  }
  const [nextUri, ...rest] = entry.remaining;
  await sonos.setUri(host, nextUri);
  await sonos.play(host);
  await writeQueue(host, { remaining: rest, current: nextUri });
  return { playing: nextUri, queued: rest.length };
}

// ------------------------------------------------------------
// Push-on-advance poller
// ------------------------------------------------------------
// One timer for the whole bridge. Every POLL_MS it reads the queue
// map and, for each host with tracks remaining, checks the player's
// transport state. A STOPPED player whose current track we still
// hold has finished, so we advance it. PLAYING / TRANSITIONING are
// left alone. A speaker that errors (powered off, off network) is
// skipped this tick rather than dropped, so it recovers on its own.
let pollTimer = null;

function startPoller() {
  if (pollTimer) return;
  pollTimer = setInterval(pollOnce, POLL_MS);
  // Do not keep the event loop alive solely for this timer.
  if (pollTimer.unref) pollTimer.unref();
}

async function pollOnce() {
  let queues;
  try {
    queues = await readQueues();
  } catch (_) {
    return;
  }
  const hosts = Object.keys(queues);
  for (const host of hosts) {
    const entry = queues[host];
    // Nothing left to advance to: drop it.
    if (!entry || !entry.remaining || entry.remaining.length === 0) {
      await writeQueue(host, null);
      continue;
    }
    let state;
    try {
      state = await sonos.getTransportState(host);
    } catch (_) {
      continue; // speaker unreachable this tick, retry next time
    }
    if (state === 'STOPPED') {
      try {
        await advance(host);
      } catch (_) {
        // advance failed (speaker hiccup), leave queue as-is to retry
      }
    }
  }
}

// Start polling as soon as the module is mounted.
startPoller();

module.exports = router;
