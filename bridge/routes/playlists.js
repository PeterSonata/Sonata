/**
 * /playlists
 *
 * A thin, clean wrapper over Jellyfin's playlist API. Sonata gets single-call
 * endpoints, never sees the Jellyfin key, and never has to juggle a userId.
 * The bridge resolves the sonata-bridge user once per process and reuses it.
 *
 * Jellyfin stays the source of truth for playlist membership, so playlists
 * already sync across every device that authenticates as sonata-bridge (per
 * the 26 May user-resolution fix). This module just gives that a tidy front
 * door and keeps the API key server-side.
 *
 *   GET  /playlists            list playlists (id, name, trackCount). No auth.
 *   GET  /playlists/:id        one playlist plus its tracks. No auth.
 *   POST /playlists            create. body { name, ids? }. Requires X-Sonata-Key.
 *   POST /playlists/:id/items  add tracks. body { ids: [...] }. Requires key.
 *
 * Remove and rename are deliberately absent. Jellyfin's
 * DELETE /Playlists/:id/Items and its playlist-update endpoint reject a
 * server API key: they need a user-scoped token and otherwise 400 with
 * "Guid can't be empty". Supporting them means the bridge logging in as the
 * sonata-bridge user via /Users/AuthenticateByName for those two calls. That
 * is a separate, small piece of work, parked until we decide to do it.
 *
 * All calls use the Node 20 native global fetch (no node-fetch, deliberately).
 */

const express = require('express');
const requireKey = require('../lib/auth');
const config = require('../lib/config');

const router = express.Router();

// Base URL without a trailing slash so path concatenation stays clean.
const JF = config.jellyfinUrl.replace(/\/+$/, '');

// Resolved once per process. The sonata-bridge user owns every Sonata-created
// playlist. Re-derived for free on restart, so it lives in memory rather than
// the persistent store.
let cachedUserId = null;

// ─── Jellyfin helper ─────────────────────────────────────────────────────────
// Attaches the API key as X-Emby-Token (same key the proxy uses), parses JSON,
// tolerates 204 no-body responses, and turns non-2xx into a thrown error that
// carries the upstream status.
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

// ─── GET /playlists ──────────────────────────────────────────────────────────
router.get('/playlists', async (req, res) => {
  try {
    const userId = await getUserId();
    const data = await jf(
      `/Users/${userId}/Items?IncludeItemTypes=Playlist&Recursive=true` +
      `&SortBy=SortName&Fields=ChildCount`
    );
    const playlists = (data.Items || []).map(p => ({
      id: p.Id,
      name: p.Name,
      trackCount: typeof p.ChildCount === 'number' ? p.ChildCount : null,
    }));
    res.json({ playlists });
  } catch (e) {
    res.status(e.status || 502).json({ error: e.message });
  }
});

// ─── GET /playlists/:id ──────────────────────────────────────────────────────
// Returns the playlist's own name plus its tracks as Jellyfin item objects, so
// Sonata's existing track rendering can consume them unchanged. PlaylistItemId
// is included on each track (needed later for removal once that lands).
router.get('/playlists/:id', async (req, res) => {
  try {
    const userId = await getUserId();
    const id = encodeURIComponent(req.params.id);
    const [meta, items] = await Promise.all([
      jf(`/Users/${userId}/Items?Ids=${id}`),
      jf(`/Playlists/${id}/Items?UserId=${userId}&Fields=Artists,AlbumArtist,Album,RunTimeTicks`),
    ]);
    const name = meta.Items && meta.Items[0] ? meta.Items[0].Name : null;
    res.json({ id: req.params.id, name, tracks: items.Items || [] });
  } catch (e) {
    res.status(e.status || 502).json({ error: e.message });
  }
});

// ─── POST /playlists ─────────────────────────────────────────────────────────
// body: { name: "My playlist", ids?: ["<itemId>", ...] }
router.post('/playlists', requireKey, async (req, res) => {
  try {
    const { name, ids } = req.body || {};
    if (!name) return res.status(400).json({ error: 'name required' });
    const userId = await getUserId();
    const params = new URLSearchParams({ Name: name, UserId: userId, MediaType: 'Audio' });
    if (Array.isArray(ids) && ids.length) params.set('Ids', ids.join(','));
    const result = await jf(`/Playlists?${params.toString()}`, { method: 'POST' });
    res.status(201).json({ id: result.Id });
  } catch (e) {
    res.status(e.status || 502).json({ error: e.message });
  }
});

// ─── POST /playlists/:id/items ───────────────────────────────────────────────
// body: { ids: ["<itemId>", ...] }
// Chunked at 50 ids per request, matching the reference integrations, to keep
// individual requests sane on large adds.
router.post('/playlists/:id/items', requireKey, async (req, res) => {
  try {
    const { ids } = req.body || {};
    if (!Array.isArray(ids) || !ids.length) {
      return res.status(400).json({ error: 'ids array required' });
    }
    const userId = await getUserId();
    const id = encodeURIComponent(req.params.id);
    for (let i = 0; i < ids.length; i += 50) {
      const chunk = ids.slice(i, i + 50).join(',');
      const params = new URLSearchParams({ Ids: chunk, UserId: userId });
      await jf(`/Playlists/${id}/Items?${params.toString()}`, { method: 'POST' });
    }
    res.status(204).end();
  } catch (e) {
    res.status(e.status || 502).json({ error: e.message });
  }
});

module.exports = router;
