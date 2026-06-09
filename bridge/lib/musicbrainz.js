/**
 * MusicBrainz lookups.
 *
 * Resolves an artist name to an MBID. Two responsibilities kept here so both
 * the /mbid route and the future photo-crawl worker share one implementation,
 * one cache, and crucially one rate limiter:
 *
 *   - 24-hour in-memory cache (artist name -> mbid).
 *   - A single system-wide 1.1-second gap between requests. MusicBrainz allows
 *     no more than one request a second. Every caller funnels through the same
 *     promise chain, so the limit holds no matter how many routes or jobs call
 *     in at once.
 *
 * lookup() throws an error with .transient = true on 5xx/429 so the caller can
 * surface a retryable status. Definitive misses are cached as null.
 */

const cache = new Map();                  // artist -> { mbid, expires }
const CACHE_MS = 24 * 60 * 60 * 1000;

let queue = Promise.resolve();
function rateLimitedFetch(url) {
  const wait = queue.then(() => new Promise(r => setTimeout(r, 1100)));
  queue = wait.catch(() => {});
  return wait.then(() => {
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), 10000);
    return fetch(url, {
      headers: { 'User-Agent': 'Sonata-Bridge/1.0 (personal music player)' },
      signal: controller.signal,
    }).finally(() => clearTimeout(t));
  });
}

async function lookup(artistRaw) {
  const artist = (artistRaw || '').trim();
  if (!artist) return { mbid: null };

  const hit = cache.get(artist);
  if (hit && hit.expires > Date.now()) {
    return { mbid: hit.mbid, cached: true };
  }

  // Strip Lucene specials, use an unquoted query for fuzzy matching.
  const clean = artist.replace(/[+\-!(){}\[\]^"~*?:\\\/]/g, ' ').replace(/\s+/g, ' ').trim();
  if (!clean) {
    cache.set(artist, { mbid: null, expires: Date.now() + CACHE_MS });
    return { mbid: null };
  }

  const url = `https://musicbrainz.org/ws/2/artist/?query=${encodeURIComponent(clean)}&limit=1&fmt=json`;
  const r = await rateLimitedFetch(url);

  if (r.status >= 500 || r.status === 429) {
    const err = new Error(`MusicBrainz returned ${r.status}`);
    err.transient = true;
    err.status = r.status;
    throw err; // transient, do not cache
  }
  if (!r.ok) {
    cache.set(artist, { mbid: null, expires: Date.now() + CACHE_MS });
    return { mbid: null };
  }

  const data = await r.json();
  const mbid = data.artists?.[0]?.id || null;
  cache.set(artist, { mbid, expires: Date.now() + CACHE_MS });
  return { mbid };
}

function stats() {
  return { mbid_cache_size: cache.size };
}

module.exports = { lookup, stats };
