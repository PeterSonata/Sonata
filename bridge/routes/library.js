/**
 * /library
 *
 * A server-side cache of the whole music library. The bridge walks Jellyfin
 * once, stores a slim per-track projection on the NAS, and serves it whole.
 * Every device then gets the library in one request instead of paginating
 * ~56,000 tracks itself over dozens of round trips. The heavy assembly moves
 * off memory-constrained mobile Safari and onto the NAS.
 *
 *   GET  /library          the whole cached library as one JSON payload.
 *                          Builds on first call if no cache exists. No auth.
 *   GET  /library/version  { version, count, builtAt } only, no tracks. Cheap.
 *                          The client polls this to decide whether to re-pull
 *                          the full library (stale-while-revalidate). No auth.
 *   POST /library/refresh  rebuild from Jellyfin in the background, return 202
 *                          immediately. Requires X-Sonata-Key.
 *
 * The slim track shape mirrors exactly the fields the Sonata client reads off
 * a Jellyfin item, with the same normalisation (the Unknown-X fallbacks, the
 * Artists[0]-or-AlbumArtist resolution). Art and stream URLs are deliberately
 * NOT cached: the client builds those from its own resolved serverUrl (LAN vs
 * remote), so baking a URL here would be wrong for some devices.
 *
 * Versioning: version is a sha1 over the slim track array, so it changes
 * whenever any track or field changes and stays put when nothing has. The
 * client compares its stored version against /library/version and only pulls
 * the full payload when they differ.
 *
 * All Jellyfin calls use the Node 20 native global fetch (no node-fetch).
 *
 * Note: jf() and getUserId() mirror the helpers in routes/playlists.js. A
 * future tidy could lift both into a shared lib/jellyfin.js; kept local here
 * to keep this change self-contained.
 */

const express = require('express');
const crypto = require('crypto');
const requireKey = require('../lib/auth');
const config = require('../lib/config');
const libstore = require('../lib/librarystore');

const router = express.Router();

// Base URL without a trailing slash so path concatenation stays clean.
const JF = config.jellyfinUrl.replace(/\/+$/, '');

// Exactly the fields the Sonata client consumes. ParentId and AlbumArtistIds
// are intentionally omitted: the client requests them but never reads them.
const FIELDS = 'AlbumArtist,Artists,Genres,IndexNumber,RunTimeTicks,AlbumId,ProductionYear';

const PAGE_SIZE = 1000;

let cachedUserId = null;
let building = null; // in-flight build promise, for single-flight

// ─── Jellyfin helper (same shape as playlists.js) ────────────────────────────
async function jf(path, opts = {}) {
  const res = await fetch(JF + path, {
    ...opts,
    headers: {
      'X-Emby-Token': config.jellyfinApiKey,
      'Content-Type': 'application/json',
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    const err = new Error(`Jellyfin ${res.status} for ${path}: ${body.slice(0, 200)}`);
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

async function getUserId() {
  if (cachedUserId) return cachedUserId;
  const users = await jf('/Users');
  const bridge = Array.isArray(users) ? users.find(u => u.Name === 'sonata-bridge') : null;
  cachedUserId = bridge ? bridge.Id : (users && users[0] && users[0].Id);
  if (!cachedUserId) throw new Error('Could not resolve a Jellyfin userId from /Users');
  return cachedUserId;
}

// ─── Slim projection ─────────────────────────────────────────────────────────
// Mirrors the client's own track mapping minus the environment-specific URLs.
// The client adds jellyfinId (= id), artSeed, artUrl, streamUrl, picture, file
// and saved on adopt.
function slim(item) {
  const artist = (item.Artists && item.Artists[0]) || item.AlbumArtist || 'Unknown Artist';
  const albumArtist = item.AlbumArtist || artist;
  return {
    id:          item.Id,
    title:       item.Name || 'Unknown Title',
    artist,
    albumArtist,
    album:       item.Album || 'Unknown Album',
    genre:       (item.Genres && item.Genres[0]) || '',
    trackNumber: item.IndexNumber || 0,
    duration:    Math.round((item.RunTimeTicks || 0) / 10000000),
    year:        item.ProductionYear || 0,
    albumId:     item.AlbumId || null,
  };
}

// ─── Build ───────────────────────────────────────────────────────────────────
// Walks the full Jellyfin audio library, projects each track, computes a
// content version and persists. Single-flight: concurrent callers (two cold
// GETs, or a GET racing a refresh) share one walk rather than starting two.
function buildLibrary() {
  if (building) return building;
  building = (async () => {
    const userId = await getUserId();
    let startIndex = 0;
    const tracks = [];
    let total = null;

    while (true) {
      const data = await jf(
        `/Users/${userId}/Items?IncludeItemTypes=Audio&Recursive=true` +
        `&Fields=${FIELDS}&SortBy=AlbumArtist,Album,IndexNumber,SortName` +
        `&SortOrder=Ascending&Limit=${PAGE_SIZE}&StartIndex=${startIndex}`
      );
      const page = data.Items || [];
      if (total === null) total = data.TotalRecordCount || 0;
      for (const item of page) tracks.push(slim(item));
      if (page.length < PAGE_SIZE) break;
      startIndex += PAGE_SIZE;
    }

    const version = crypto.createHash('sha1')
      .update(JSON.stringify(tracks))
      .digest('hex')
      .slice(0, 12);
    const meta = { version, count: tracks.length, builtAt: Date.now() };
    await libstore.save(meta, tracks);
    console.log(`library: built ${meta.count} tracks, version ${meta.version}`);
    return meta;
  })().finally(() => { building = null; });
  return building;
}

// ─── GET /library ────────────────────────────────────────────────────────────
router.get('/library', async (req, res) => {
  try {
    let body = await libstore.getBody();
    if (body === null) {
      await buildLibrary();
      body = await libstore.getBody();
    }
    res.type('application/json').send(body);
  } catch (e) {
    res.status(e.status || 502).json({ error: e.message });
  }
});

// ─── GET /library/version ────────────────────────────────────────────────────
router.get('/library/version', async (req, res) => {
  try {
    const meta = await libstore.getMeta();
    res.json(meta || { version: null, count: 0, builtAt: null });
  } catch (e) {
    res.status(502).json({ error: e.message });
  }
});

// ─── POST /library/refresh ───────────────────────────────────────────────────
// Kicks a background rebuild and returns immediately. The single-flight guard
// means firing this while a build is already running reuses that build.
router.post('/library/refresh', requireKey, async (req, res) => {
  buildLibrary().catch(err => console.error('library rebuild failed:', err.message));
  const meta = await libstore.getMeta();
  res.status(202).json({
    status: 'rebuilding',
    current: meta || { version: null, count: 0, builtAt: null },
  });
});

module.exports = router;
