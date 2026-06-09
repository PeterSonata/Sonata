/**
 * Jellyfin proxy.
 *
 * Everything under /jellyfin/* is forwarded to Jellyfin with the API key
 * attached, so the browser never sees the key. Behaviour is unchanged from the
 * original single-file bridge:
 *
 *   - API key attached both as a header (for fetch/XHR) and as an api_key query
 *     param (so <img> and <audio> tags, which cannot set headers, still work).
 *   - CORS headers forced in the proxyRes callback, overriding upstream and set
 *     before streaming begins. This is the bit DSM's reverse proxy GUI cannot
 *     do, since it writes proxy_set_header rather than add_header always.
 */

const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const config = require('../lib/config');

const router = express.Router();

router.use('/jellyfin', createProxyMiddleware({
  target: config.jellyfinUrl,
  changeOrigin: true,
  pathRewrite: { '^/jellyfin': '' },
  on: {
    proxyReq: (proxyReq, req) => {
      proxyReq.setHeader('X-Emby-Token', config.jellyfinApiKey);
      const path = proxyReq.path;
      if (!/[?&]api_key=/.test(path)) {
        const sep = path.includes('?') ? '&' : '?';
        proxyReq.path = path + sep + 'api_key=' + encodeURIComponent(config.jellyfinApiKey);
      }
    },
    proxyRes: (proxyRes) => {
      delete proxyRes.headers['set-cookie'];
      proxyRes.headers['access-control-allow-origin']   = '*';
      proxyRes.headers['access-control-allow-methods']  = 'GET, POST, PUT, DELETE, OPTIONS';
      proxyRes.headers['access-control-allow-headers']  = 'Content-Type, Authorization, X-Emby-Authorization, X-Emby-Token';
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

module.exports = router;
