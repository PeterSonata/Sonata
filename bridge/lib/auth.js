/**
 * Writable-route guard.
 *
 * Apply this middleware to any route that changes state (playlist POST,
 * library refresh, job enqueue). It checks the X-Sonata-Key header against
 * SONATA_KEY from .env using a timing-safe comparison.
 *
 * Fails closed: if SONATA_KEY is not configured, every guarded request is
 * refused with 503. That way a misconfigured bridge never silently exposes
 * writable endpoints to the open internet.
 *
 * Usage:
 *   const requireKey = require('../lib/auth');
 *   router.post('/playlists', requireKey, handler);
 */

const crypto = require('crypto');
const config = require('./config');

module.exports = function requireKey(req, res, next) {
  const expected = config.sonataKey;
  if (!expected) {
    return res.status(503).json({ error: 'SONATA_KEY not configured on the bridge' });
  }

  const provided = req.get('X-Sonata-Key') || '';
  const a = Buffer.from(provided);
  const b = Buffer.from(expected);

  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) {
    return res.status(401).json({ error: 'Invalid or missing X-Sonata-Key' });
  }

  next();
};
