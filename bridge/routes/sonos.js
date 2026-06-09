// routes/sonos.js
// ============================================================
// Sonos control endpoints for the bridge.
//
// Read endpoints (open):
//   GET  /sonos                 list discovered + configured players
//
// Control endpoints (require X-Sonata-Key):
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
    const players = await sonos.discover(3000);
    res.json({
      players,
      configured: sonos.configuredHosts(),
      count: players.length,
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ------------------------------------------------------------
// Control: play a list (or single) of URIs from the start
// ------------------------------------------------------------
router.post('/sonos/play', auth, async (req, res) => {
  const { host } = req.body || {};
  let { uris, uri } = req.body || {};
  if (!host) return res.status(400).json({ error: 'host required' });

  if (!uris && uri) uris = [uri];
  if (!Array.isArray(uris) || uris.length === 0) {
    return res.status(400).json({ error: 'uris (array) or uri required' });
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
// Control: transport
// ------------------------------------------------------------
function transportRoute(path, fn) {
  router.post(path, auth, async (req, res) => {
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
router.post('/sonos/next', auth, async (req, res) => {
  const { host } = req.body || {};
  if (!host) return res.status(400).json({ error: 'host required' });
  try {
    const advanced = await advance(host);
    res.json({ ok: true, ...advanced });
  } catch (err) {
    res.status(502).json({ error: err.message });
  }
});

router.post('/sonos/volume', auth, async (req, res) => {
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
