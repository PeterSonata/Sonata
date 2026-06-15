#!/usr/bin/env python3
# sonata_bridge_sonos_state.py
# ------------------------------------------------------------------
# Adds a read endpoint to the Sonos route: GET /sonos/state?host=...
#
# Why: the bridge already holds the current track per host in its
# push-on-advance queue ({ remaining, current }) and the poller moves
# it through the queue on natural track ends, but nothing exposes the
# current track to the client. So the desktop now-playing pane only
# follows manual prev/next and goes stale when the speaker advances on
# its own. This endpoint lets the client poll and follow the speaker.
#
# It returns the Jellyfin item id parsed out of the stored stream URL
# (not the URL itself), so the embedded api_key is never exposed over
# the external forward. Uses only existing helpers (readQueues,
# sonos.getTransportState) and is gated by the same lanOrAuth guard as
# the control routes.
#
# Idempotent, timestamped backup, fails loud on a missing or non-unique
# anchor. Run from the repo root:
#   python scripts\sonata_bridge_sonos_state.py
# Then deploy: scp -O bridge\routes\sonos.js to
#   /volume1/sonata-bridge/routes/sonos.js  and restart PM2.
# ------------------------------------------------------------------

import sys
import shutil
import datetime
from pathlib import Path

SONOS = Path('bridge/routes/sonos.js')
MARKER = "'/sonos/state'"

ANCHOR = (
    "// ------------------------------------------------------------\n"
    "// Control: transport\n"
    "// ------------------------------------------------------------\n"
)

INSERT = (
    "// ------------------------------------------------------------\n"
    "// Read: current playback state for a host\n"
    "// ------------------------------------------------------------\n"
    "// The client polls this to follow the speaker: as the push-on-\n"
    "// advance poller moves through the queue on natural track ends,\n"
    "// the client reads currentId and points its display at the\n"
    "// matching queue entry. We return the Jellyfin item id parsed out\n"
    "// of the stored stream URL rather than the URL itself, so the\n"
    "// embedded api_key is never exposed over the external forward.\n"
    "router.get('/sonos/state', lanOrAuth, async (req, res) => {\n"
    "  const host = req.query.host;\n"
    "  if (!host) return res.status(400).json({ error: 'host required' });\n"
    "  try {\n"
    "    const queues = await readQueues();\n"
    "    const entry = queues[host] || null;\n"
    "    let currentId = null;\n"
    "    if (entry && entry.current) {\n"
    "      const m = String(entry.current).match(/\\/Audio\\/([^/]+)\\/stream/);\n"
    "      if (m) currentId = decodeURIComponent(m[1]);\n"
    "    }\n"
    "    let transport = null;\n"
    "    try { transport = await sonos.getTransportState(host); } catch (_) {}\n"
    "    res.json({\n"
    "      active: !!entry,\n"
    "      currentId,\n"
    "      remaining: entry && entry.remaining ? entry.remaining.length : 0,\n"
    "      transport,\n"
    "    });\n"
    "  } catch (err) {\n"
    "    res.status(502).json({ error: err.message });\n"
    "  }\n"
    "});\n"
    "\n"
)


def die(msg):
    print('ABORT: ' + msg)
    sys.exit(1)


def main():
    if not SONOS.exists():
        die(f'{SONOS} not found. Run from the repo root.')
    src = SONOS.read_text(encoding='utf-8')

    if MARKER in src:
        print('Already applied (/sonos/state present). Nothing to do.')
        return

    n = src.count(ANCHOR)
    if n == 0:
        die('transport-section anchor not found.')
    if n > 1:
        die(f'transport-section anchor not unique ({n} matches).')

    out = src.replace(ANCHOR, INSERT + ANCHOR, 1)
    if MARKER not in out:
        die('post-patch sanity check failed; not writing.')

    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = SONOS.with_suffix(f'.backup-{ts}.js')
    shutil.copy2(SONOS, backup)
    SONOS.write_text(out, encoding='utf-8')
    print(f'Patched {SONOS} (backup: {backup.name}).')
    print('Added GET /sonos/state. Deploy via scp -O then restart PM2.')


if __name__ == '__main__':
    main()
