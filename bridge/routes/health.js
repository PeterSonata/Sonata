/**
 * /health and /stats.
 */

const express = require('express');
const config = require('../lib/config');
const musicbrainz = require('../lib/musicbrainz');
const fanart = require('../lib/fanart');

const router = express.Router();

router.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    jellyfin: config.jellyfinUrl,
    fanart_configured: !!config.fanartApiKey,
    auth_configured: !!config.sonataKey,
    uptime_seconds: Math.round(process.uptime()),
  });
});

router.get('/stats', (req, res) => {
  res.json({
    ...fanart.stats(),
    ...musicbrainz.stats(),
    uptime_seconds: Math.round(process.uptime()),
    memory_mb: Math.round(process.memoryUsage().heapUsed / 1024 / 1024),
  });
});

module.exports = router;
