const express = require('express');
const fanart = require('../lib/fanart');

const router = express.Router();

router.get('/fanart/:mbid', async (req, res) => {
  try {
    const data = await fanart.lookup(req.params.mbid);
    res.json(data);
  } catch (e) {
    if (e.status) {
      if (e.status >= 500) console.warn(`[fanart] ${e.status} for ${req.params.mbid}`);
      return res.status(e.status).json({ error: e.message });
    }
    console.error(`[fanart] error for ${req.params.mbid}:`, e.message);
    res.status(502).json({ error: 'fanart.tv upstream error', detail: e.message });
  }
});

module.exports = router;
