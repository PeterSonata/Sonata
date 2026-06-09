/**
 * Artist photo cache.
 *
 * Resolves artist -> MusicBrainz MBID -> fanart.tv images, downloads the bytes
 * to the NAS, and serves them back. The crawl happens once, server-side, so
 * every device benefits from one crawl instead of each phone and laptop
 * independently hammering MusicBrainz and fanart.tv for hours.
 *
 * Shape of one cached entry in the store under the "photos" key:
 *
 *   {
 *     "Fugazi": {
 *       mbid: "233fc3f3-...",
 *       thumb: "233fc3f3-...-thumb.jpg",   // filename in data/photos, or null
 *       bg:    "233fc3f3-...-bg.jpg",      // filename, or null
 *       status: "ok" | "none" | "no-mbid",
 *       checkedAt: "2026-06-09T..."
 *     }
 *   }
 *
 *   status meanings:
 *     ok      photo downloaded, thumb (and maybe bg) on disk
 *     none    MBID found but fanart.tv has no artist images
 *     no-mbid MusicBrainz could not resolve the name
 *
 *   Any of these three is a settled result and is skipped on re-crawl. An
 *   artist that errored transiently (MusicBrainz 5xx/429) is left absent from
 *   the map so the next crawl retries it.
 *
 * The crawl is a background job, not a synchronous route. POST /photos/crawl
 * enqueues it; the worker drains it. The job processes a small batch then, if
 * artists remain, re-enqueues itself. So one kick works through the whole
 * backlog over many worker ticks, picks up where it left off after a restart,
 * and never locks the store for hours.
 *
 * Endpoints:
 *   GET  /photos             whole map + status summary (read-only)
 *   GET  /photos/img/:file   image bytes, long cache (read-only)
 *   GET  /photos/:artist     one artist's entry, 404 if uncrawled/none (read-only)
 *   POST /photos/crawl       enqueue a crawl, body { artists?: [...] } (keyed)
 */

const express = require('express');
const store = require('../lib/store');
const auth = require('../lib/auth');
const worker = require('../lib/worker');
const musicbrainz = require('../lib/musicbrainz');
const fanart = require('../lib/fanart');
const photostore = require('../lib/photostore');

const router = express.Router();

// How many artists one job invocation handles before re-enqueuing itself.
// At ~1.1s per MusicBrainz lookup a batch of 20 is roughly 25s of work, a
// comfortable unit that commits often and survives restarts cheaply.
const BATCH = 20;

// ─── Helpers ────────────────────────────────────────────────────────────────

// Pick the best image url from a fanart.tv response section. fanart returns
// entries with a `likes` count; highest likes wins. Returns null if empty.
function bestImage(list) {
  if (!Array.isArray(list) || list.length === 0) return null;
  const sorted = [...list].sort((a, b) => (Number(b.likes) || 0) - (Number(a.likes) || 0));
  return sorted[0]?.url || null;
}

// Download an image URL to a buffer. Returns { buffer, contentType } or throws.
async function download(url) {
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), 15000);
  let r;
  try {
    r = await fetch(url, { signal: controller.signal });
  } finally {
    clearTimeout(t);
  }
  if (!r.ok) {
    const err = new Error(`image download returned ${r.status}`);
    if (r.status >= 500 || r.status === 429) err.transient = true;
    throw err;
  }
  const contentType = r.headers.get('content-type') || '';
  const buffer = Buffer.from(await r.arrayBuffer());
  return { buffer, contentType };
}

// Process one artist end to end. Returns the store entry to record, or null
// if the artist should be left absent (transient failure, retry next crawl).
async function crawlArtist(artist) {
  let mb;
  try {
    mb = await musicbrainz.lookup(artist);
  } catch (e) {
    if (e.transient) return null; // leave absent, retry later
    throw e;
  }

  if (!mb.mbid) {
    return { mbid: null, thumb: null, bg: null, status: 'no-mbid', checkedAt: new Date().toISOString() };
  }

  let art;
  try {
    art = await fanart.lookup(mb.mbid);
  } catch (e) {
    if (e.status && e.status >= 500) return null; // transient fanart, retry
    if (e.status === 429) return null;
    // 503 (not configured) or 4xx: settle as none rather than spinning
    return { mbid: mb.mbid, thumb: null, bg: null, status: 'none', checkedAt: new Date().toISOString() };
  }

  const thumbUrl = bestImage(art.artistthumb);
  const bgUrl = bestImage(art.artistbackground);

  if (!thumbUrl && !bgUrl) {
    return { mbid: mb.mbid, thumb: null, bg: null, status: 'none', checkedAt: new Date().toISOString() };
  }

  let thumbName = null;
  let bgName = null;

  if (thumbUrl) {
    try {
      const { buffer, contentType } = await download(thumbUrl);
      thumbName = `${mb.mbid}-thumb.${photostore.extFor(thumbUrl, contentType)}`;
      await photostore.write(thumbName, buffer);
    } catch (e) {
      if (e.transient) return null; // retry the whole artist later
      thumbName = null; // permanent download failure, carry on without thumb
    }
  }

  if (bgUrl) {
    try {
      const { buffer, contentType } = await download(bgUrl);
      bgName = `${mb.mbid}-bg.${photostore.extFor(bgUrl, contentType)}`;
      await photostore.write(bgName, buffer);
    } catch (e) {
      bgName = null; // background is optional, never fail the artist for it
    }
  }

  if (!thumbName && !bgName) {
    // Both downloads failed non-transiently. Record none so we don't loop.
    return { mbid: mb.mbid, thumb: null, bg: null, status: 'none', checkedAt: new Date().toISOString() };
  }

  return { mbid: mb.mbid, thumb: thumbName, bg: bgName, status: 'ok', checkedAt: new Date().toISOString() };
}

// ─── The crawl job handler ───────────────────────────────────────────────────
// payload.queue is the list of artist names still to do. We take BATCH off the
// front, process them, write results, then re-enqueue ourselves with the rest.
worker.register('photo-crawl', async (payload) => {
  const queue = Array.isArray(payload.queue) ? payload.queue : [];
  const batch = queue.slice(0, BATCH);
  const rest = queue.slice(BATCH);

  let settled = 0;     // artists that got a fresh store entry this run
  let withPhotos = 0;  // of those, how many actually got an image on disk
  let skipped = 0;     // already settled before we reached them

  for (const artist of batch) {
    // Skip if already settled since the crawl was enqueued.
    const existing = (await store.get('photos')) || {};
    if (existing[artist] && existing[artist].status) {
      skipped++;
      continue;
    }
    const entry = await crawlArtist(artist);
    if (entry) {
      await store.update('photos', (photos = {}) => ({ ...photos, [artist]: entry }));
      settled++;
      if (entry.status === 'ok') withPhotos++;
    }
  }

  // More to do: re-enqueue the remainder as a fresh job. The worker drains it
  // on a later tick, so the crawl self-paces across ticks and survives restart.
  if (rest.length > 0) {
    await worker.enqueue('photo-crawl', { queue: rest });
  }

  return { processed: batch.length, settled, withPhotos, skipped, remaining: rest.length };
});

// ─── GET /photos : whole map + summary ───────────────────────────────────────
router.get('/photos', async (req, res) => {
  const photos = (await store.get('photos')) || {};
  const summary = { total: 0, ok: 0, none: 0, 'no-mbid': 0 };
  for (const k of Object.keys(photos)) {
    summary.total++;
    const s = photos[k].status;
    if (s in summary) summary[s]++;
  }
  res.json({ summary, photos });
});

// ─── GET /photos/img/:file : the image bytes ─────────────────────────────────
// Long cache: images are keyed by MBID and never change, so a year is safe.
router.get('/photos/img/:file', async (req, res) => {
  const { file } = req.params;
  if (!photostore.isSafeName(file)) {
    return res.status(400).json({ error: 'bad filename' });
  }
  if (!(await photostore.exists(file))) {
    return res.status(404).json({ error: 'not found' });
  }
  res.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
  res.sendFile(photostore.fullPath(file));
});

// ─── GET /photos/:artist : one artist ────────────────────────────────────────
router.get('/photos/:artist', async (req, res) => {
  const artist = req.params.artist;
  const photos = (await store.get('photos')) || {};
  const entry = photos[artist];

  if (!entry) {
    return res.status(404).json({ status: 'not-crawled', artist });
  }
  if (entry.status !== 'ok') {
    return res.status(404).json({ status: entry.status, artist });
  }

  res.json({
    artist,
    mbid: entry.mbid,
    thumb: entry.thumb ? `/photos/img/${entry.thumb}` : null,
    bg: entry.bg ? `/photos/img/${entry.bg}` : null,
    checkedAt: entry.checkedAt,
  });
});

// ─── POST /photos/crawl : enqueue a crawl (keyed) ────────────────────────────
// Body { artists: [...] } crawls that set. Empty body crawls every artist in
// the body's `artists` that is not already settled. The client passes its full
// artist list; the bridge filters to the uncrawled ones so re-kicks are cheap.
router.post('/photos/crawl', auth, async (req, res) => {
  const requested = Array.isArray(req.body?.artists) ? req.body.artists : null;
  if (!requested || requested.length === 0) {
    return res.status(400).json({ error: 'body must include a non-empty artists array' });
  }

  const photos = (await store.get('photos')) || {};
  // Only queue artists with no settled entry yet. Dedupe and drop blanks.
  const seen = new Set();
  const queue = [];
  for (const a of requested) {
    const name = (a || '').trim();
    if (!name || seen.has(name)) continue;
    seen.add(name);
    if (photos[name] && photos[name].status) continue; // already settled
    queue.push(name);
  }

  if (queue.length === 0) {
    return res.json({ enqueued: false, reason: 'all requested artists already crawled', queued: 0 });
  }

  const job = await worker.enqueue('photo-crawl', { queue });
  res.status(202).json({ enqueued: true, jobId: job.id, queued: queue.length });
});

module.exports = router;
