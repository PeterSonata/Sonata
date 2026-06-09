/**
 * /jobs
 *
 * Exposes the background job queue. This route is also the test harness that
 * proves the three new foundation pieces work together: the store persists the
 * queue, the auth middleware guards the writable side, and the worker drains it.
 *
 *   GET  /jobs   read-only queue status, no auth (metadata only).
 *   POST /jobs   enqueue a job, requires X-Sonata-Key.
 *                body: { "type": "echo", "payload": { "hello": "world" } }
 *
 * Once real handlers exist (photo crawl, etc.) this route stays useful for
 * inspecting and kicking off work.
 */

const express = require('express');
const requireKey = require('../lib/auth');
const store = require('../lib/store');
const worker = require('../lib/worker');

const router = express.Router();

router.get('/jobs', async (req, res) => {
  const jobs = (await store.get('jobs')) || [];
  const counts = jobs.reduce((acc, j) => {
    acc[j.status] = (acc[j.status] || 0) + 1;
    return acc;
  }, {});
  res.json({ counts, jobs });
});

router.post('/jobs', requireKey, async (req, res) => {
  const { type, payload } = req.body || {};
  if (!type) return res.status(400).json({ error: 'type required' });
  const job = await worker.enqueue(type, payload || {});
  res.status(202).json({ enqueued: job.id, type: job.type });
});

module.exports = router;
