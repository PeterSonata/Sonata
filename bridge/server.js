/**
 * Sonata Bridge, entry point.
 *
 * This file is deliberately thin. All real logic lives in lib/ and routes/.
 * It only loads config, wires middleware in the right order, mounts the
 * routers, and starts the worker.
 *
 *   lib/config.js       env loading and validation
 *   lib/store.js        atomic JSON store (data + job queue)
 *   lib/auth.js         X-Sonata-Key guard for writable routes
 *   lib/worker.js       in-process background job runner
 *   lib/musicbrainz.js  rate-limited MB lookups + cache
 *   lib/fanart.js       fanart.tv lookups + cache
 *   routes/*            one router per endpoint group
 *
 * Start under PM2 with --cwd /volume1/sonata-bridge so .env resolves.
 */

const express = require('express');
const config = require('./lib/config');
const worker = require('./lib/worker');

const app = express();

// ─── CORS (applies to everything) ───────────────────────────────────────────
// X-Sonata-Key added to allowed headers so browser clients can authenticate
// to writable routes.
app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Emby-Authorization, X-Emby-Token, X-Sonata-Key');
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  next();
});

// ─── Jellyfin proxy: mounted BEFORE the body parser ─────────────────────────
// http-proxy-middleware streams the raw request body upstream. If express.json()
// runs first it consumes that stream and any proxied POST hangs. So the proxy
// goes first, the body parser second.
app.use(require('./routes/jellyfin'));

// ─── Body parser for everything after the proxy ─────────────────────────────
app.use(express.json());

// ─── Routes ─────────────────────────────────────────────────────────────────
app.use(require('./routes/health'));
app.use(require('./routes/fanart'));
app.use(require('./routes/mbid'));
app.use(require('./routes/jobs'));
app.use(require('./routes/playlists'));

// ─── Start ────────────────────────────────────────────────────────────────
app.listen(config.bridgePort, async () => {
  console.log(`Sonata Bridge listening on port ${config.bridgePort}`);
  console.log(`  Jellyfin:  ${config.jellyfinUrl}`);
  console.log(`  fanart.tv: ${config.fanartApiKey ? 'configured' : 'NOT configured'}`);
  console.log(`  Auth key:  ${config.sonataKey ? 'configured' : 'NOT configured (writable routes disabled)'}`);
  console.log(`  Endpoints: /health, /stats, /jellyfin/*, /fanart/:mbid, /mbid, /jobs`);

  await worker.resetStuckJobs();
  worker.start({ intervalMs: 2000 });
});

process.on('SIGINT',  () => { console.log('Shutting down…'); process.exit(0); });
process.on('SIGTERM', () => { console.log('Shutting down…'); process.exit(0); });
