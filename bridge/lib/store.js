/**
 * Atomic JSON store.
 *
 * A tiny key-value store persisted to data/store.json. This is the canonical
 * place the bridge keeps its own state: playlists, the photo cache index, the
 * job queue, and anything else added later.
 *
 * Two guarantees matter here:
 *
 *   1. Atomic writes. Every save goes to a temp file then renames it over the
 *      real file. Rename is atomic on the same filesystem, so a crash or power
 *      cut mid-write can never leave a half-written store.json behind.
 *
 *   2. Serialised read-modify-write. An in-process promise queue serialises
 *      every update so two concurrent callers cannot read the same value and
 *      clobber each other. One process, so an in-process mutex is enough.
 *
 * The path is resolved relative to this file, not the working directory, so
 * the store lives at /volume1/sonata-bridge/data/store.json regardless of how
 * the process was launched.
 */

const fs = require('fs');
const fsp = fs.promises;
const path = require('path');

const DATA_DIR   = path.join(__dirname, '..', 'data');
const STORE_FILE = path.join(DATA_DIR, 'store.json');
const TMP_FILE   = path.join(DATA_DIR, 'store.json.tmp');

let cache = null;           // in-memory mirror, loaded once
let queue = Promise.resolve(); // mutex for read-modify-write

async function load() {
  if (cache) return cache;
  try {
    const raw = await fsp.readFile(STORE_FILE, 'utf8');
    cache = JSON.parse(raw);
  } catch (e) {
    if (e.code === 'ENOENT') {
      cache = {};
    } else {
      // Corrupt or unreadable: fail loud rather than silently wiping state.
      throw new Error(`store.json unreadable: ${e.message}`);
    }
  }
  return cache;
}

async function persist(data) {
  await fsp.mkdir(DATA_DIR, { recursive: true });
  await fsp.writeFile(TMP_FILE, JSON.stringify(data, null, 2), 'utf8');
  await fsp.rename(TMP_FILE, STORE_FILE);
  cache = data;
}

function run(fn) {
  const result = queue.then(fn);
  // Keep the chain alive even if this op rejects, so later ops still run.
  queue = result.catch(() => {});
  return result;
}

// ─── Public API ───────────────────────────────────────────────────────────

async function get(key) {
  const data = await load();
  return data[key];
}

async function all() {
  const data = await load();
  return { ...data };
}

async function set(key, value) {
  return run(async () => {
    const data = await load();
    data[key] = value;
    await persist(data);
    return value;
  });
}

// Read-modify-write. fn receives the current value (may be undefined) and
// returns the new value. The whole thing runs inside the mutex.
async function update(key, fn) {
  return run(async () => {
    const data = await load();
    const next = await fn(data[key]);
    data[key] = next;
    await persist(data);
    return next;
  });
}

module.exports = { get, all, set, update };
