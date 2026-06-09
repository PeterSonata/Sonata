/**
 * /mbid?artist=NAME
 *
 * Thin wrapper over lib/musicbrainz. The lookup, cache and rate limiting all
 * live in the lib so the worker can call the same code path directly.
 */

const express = require('express');
const musicbrainz = require('../lib/musicbrainz');

const router = express.Router();

router.get('/mbid', async (req, res) => {
  const artist = (req.query.artist || '').trim();
  if (!artist) return res.status(400).json({ error: 'artist parameter required' });

  try {
    const out = await musicbrainz.lookup(artist);
    res.json(out);
  } catch (e) {
    if (e.transient) {
      console.warn(`[mbid] transient ${e.status} for "${artist}"`);
      return res.status(e.status).json({ error: e.message });
    }
    console.error(`[mbid] error for "${artist}":`, e.message);
    res.status(502).json({ error: 'MusicBrainz upstream error', detail: e.message });
  }
});

module.exports = router;
