/**
 * Library store.
 *
 * Holds the cached music library as a single file at data/library.json,
 * deliberately separate from the key-value store.js. The library blob is
 * large (tens of thousands of tracks), and store.json rewrites its entire
 * contents on every small write (a job status, a queue change). Putting the
 * library inside it would mean rewriting the whole library on every unrelated
 * update. A dedicated file avoids that write amplification while keeping the
 * same atomic discipline.
 *
 * Atomic writes: every save goes to a temp file then renames it over the real
 * file. Rename is atomic on the same filesystem, so a crash mid-write can
 * never leave a half-written library.json behind.
 *
 * In-memory mirror: the serialised JSON string and the small meta object are
 * held in memory so GET /library serves without re-reading or re-serialising,
 * and GET /library/version answers from meta alone. On a fresh process the
 * first access lazy-loads from disk once, then everything is in memory.
 *
 * The file shape is { version, count, builtAt, tracks: [...] }. Unlike
 * store.json this is written compact (no pretty-print) since it is machine-only
 * and large.
 */

const fs = require('fs');
const fsp = fs.promises;
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const LIB_FILE = path.join(DATA_DIR, 'library.json');
const TMP_FILE = path.join(DATA_DIR, 'library.json.tmp');

let loaded = false;     // have we tried to read the file this process?
let bodyCache = null;   // serialised JSON string of the whole payload, or null
let metaCache = null;   // { version, count, builtAt }, or null

async function ensureLoaded() {
  if (loaded) return;
  try {
    const raw = await fsp.readFile(LIB_FILE, 'utf8');
    const parsed = JSON.parse(raw);
    bodyCache = raw;
    metaCache = {
      version: parsed.version,
      count: parsed.count,
      builtAt: parsed.builtAt,
    };
  } catch (e) {
    if (e.code === 'ENOENT') {
      bodyCache = null;
      metaCache = null;
    } else {
      // Corrupt or unreadable: fail loud rather than silently serving nothing.
      throw new Error(`library.json unreadable: ${e.message}`);
    }
  }
  loaded = true;
}

// ─── Public API ───────────────────────────────────────────────────────────

// The whole payload as a ready-to-send JSON string, or null if no cache yet.
async function getBody() {
  await ensureLoaded();
  return bodyCache;
}

// Just { version, count, builtAt }, or null if no cache yet. Cheap: never
// touches the tracks array.
async function getMeta() {
  await ensureLoaded();
  return metaCache;
}

// Persist a freshly built library. meta is { version, count, builtAt },
// tracks is the slim track array. Returns the stored meta.
async function save(meta, tracks) {
  const payload = {
    version: meta.version,
    count: meta.count,
    builtAt: meta.builtAt,
    tracks,
  };
  const body = JSON.stringify(payload);
  await fsp.mkdir(DATA_DIR, { recursive: true });
  await fsp.writeFile(TMP_FILE, body, 'utf8');
  await fsp.rename(TMP_FILE, LIB_FILE);
  bodyCache = body;
  metaCache = { version: meta.version, count: meta.count, builtAt: meta.builtAt };
  loaded = true;
  return metaCache;
}

module.exports = { getBody, getMeta, save };
