const config = require('./config');

const cache = new Map();                  // mbid -> { data, expires }
const CACHE_MS = 24 * 60 * 60 * 1000;

async function lookup(mbid) {
  if (!config.fanartApiKey) {
    const err = new Error('fanart.tv not configured');
    err.status = 503;
    throw err;
  }
  if (!/^[0-9a-f-]{30,40}$/i.test(mbid)) {
    const err = new Error('Invalid MBID format');
    err.status = 400;
    throw err;
  }

  const hit = cache.get(mbid);
  if (hit && hit.expires > Date.now()) {
    return hit.data;
  }

  const url = `https://webservice.fanart.tv/v3/music/${mbid}?api_key=${config.fanartApiKey}`;
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), 8000);
  let r;
  try {
    r = await fetch(url, { signal: controller.signal });
  } finally {
    clearTimeout(t);
  }

  if (r.status === 404) {
    const empty = { artistthumb: [], artistbackground: [] };
    cache.set(mbid, { data: empty, expires: Date.now() + CACHE_MS });
    return empty;
  }
  if (!r.ok) {
    const err = new Error(`fanart.tv returned ${r.status}`);
    err.status = r.status;
    throw err;
  }

  const data = await r.json();
  cache.set(mbid, { data, expires: Date.now() + CACHE_MS });
  return data;
}

function stats() {
  return { fanart_cache_size: cache.size };
}

module.exports = { lookup, stats };
