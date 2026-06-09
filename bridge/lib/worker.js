/**
 * In-process background job runner.
 *
 * No Redis, no second process, no external queue. For a single NAS running a
 * single PM2 process, with work that is deliberately rate-limited (the photo
 * crawl is one MusicBrainz request a second), an in-process worker is the
 * right weight. Anything heavier would be overengineering.
 *
 * How it works:
 *
 *   - Jobs live in the atomic store under the "jobs" key, so they survive a
 *     restart.
 *   - A timer ticks every couple of seconds. On each tick the worker drains
 *     every pending job, one at a time, calling the handler registered for
 *     that job's type.
 *   - Handlers are registered by other modules. The future photo crawl will
 *     do register('photo-crawl', fn) and then enqueue('photo-crawl', {...}).
 *
 * A built-in "echo" handler is registered at the bottom purely so the
 * foundation can be tested end to end before any real job exists. Delete it
 * once real handlers are wired up.
 */

const crypto = require('crypto');
const store = require('./store');

const handlers = Object.create(null); // type -> async (payload, job) => result

function register(type, fn) {
  handlers[type] = fn;
}

async function enqueue(type, payload = {}) {
  const job = {
    id: crypto.randomUUID(),
    type,
    payload,
    status: 'pending',
    created: new Date().toISOString(),
    started: null,
    finished: null,
    result: null,
    error: null,
  };
  await store.update('jobs', (jobs = []) => [...jobs, job]);
  return job;
}

// Atomically pick the next pending job and flip it to running, so two ticks
// can never claim the same job.
async function claimNext() {
  let claimed = null;
  await store.update('jobs', (jobs = []) => {
    const job = jobs.find(j => j.status === 'pending');
    if (job) {
      job.status = 'running';
      job.started = new Date().toISOString();
      claimed = job;
    }
    return jobs;
  });
  return claimed;
}

async function finish(id, patch) {
  await store.update('jobs', (jobs = []) =>
    jobs.map(j => (j.id === id ? { ...j, ...patch, finished: new Date().toISOString() } : j))
  );
}

let timer = null;
let busy = false;

async function tick() {
  if (busy) return; // never run two drains at once
  busy = true;
  try {
    let job;
    while ((job = await claimNext())) {
      const handler = handlers[job.type];
      if (!handler) {
        console.warn(`[worker] no handler for job type "${job.type}" (${job.id})`);
        await finish(job.id, { status: 'failed', error: `no handler for type "${job.type}"` });
        continue;
      }
      try {
        const result = await handler(job.payload, job);
        await finish(job.id, { status: 'done', result: result ?? null });
        console.log(`[worker] job ${job.id} (${job.type}) done`);
      } catch (e) {
        console.error(`[worker] job ${job.id} (${job.type}) failed:`, e.message);
        await finish(job.id, { status: 'failed', error: e.message });
      }
    }
  } finally {
    busy = false;
  }
}

// Any job left "running" was interrupted by a restart. Reset it to pending so
// it gets retried on the next tick.
async function resetStuckJobs() {
  await store.update('jobs', (jobs = []) =>
    jobs.map(j => (j.status === 'running' ? { ...j, status: 'pending', started: null } : j))
  );
}

function start({ intervalMs = 2000 } = {}) {
  if (timer) return;
  timer = setInterval(() => {
    tick().catch(e => console.error('[worker] tick error:', e.message));
  }, intervalMs);
  tick().catch(() => {}); // kick once at boot
  console.log(`[worker] started, polling every ${intervalMs}ms`);
}

// ─── Built-in demo handler (safe to delete later) ───────────────────────────
register('echo', async (payload) => {
  console.log('[worker] echo:', JSON.stringify(payload));
  return { echoed: payload };
});

module.exports = { register, enqueue, start, resetStuckJobs };
