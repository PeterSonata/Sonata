/**
 * Centralised configuration.
 *
 * Loads .env once and validates it. Every other module imports config from
 * here rather than reaching into process.env directly, so there is a single
 * place that knows the shape of the environment.
 *
 * dotenv is configured here, so importing this module guarantees .env has
 * been read. Start the process under PM2 with --cwd /volume1/sonata-bridge
 * so the .env in that directory resolves.
 */

require('dotenv').config();

const config = {
  jellyfinUrl:    process.env.JELLYFIN_URL || 'http://192.168.1.83:8096',
  jellyfinApiKey: process.env.JELLYFIN_API_KEY,
  fanartApiKey:   process.env.FANART_API_KEY,
  sonataKey:      process.env.SONATA_KEY,
  bridgePort:     parseInt(process.env.BRIDGE_PORT || '8443', 10),
};

if (!config.jellyfinApiKey) {
  console.error('FATAL: JELLYFIN_API_KEY missing from .env');
  process.exit(1);
}
if (!config.fanartApiKey) {
  console.warn('WARNING: FANART_API_KEY missing from .env, artist photos will not work');
}
if (!config.sonataKey) {
  console.warn('WARNING: SONATA_KEY missing from .env, writable endpoints will refuse every request until it is set');
}

module.exports = config;
