#!/usr/bin/env python3
# sonata_cast_follow.py
# ------------------------------------------------------------------
# Makes the now-playing display follow the casting speaker.
#
# Problem: while casting, the display is set once at cast start and
# again on manual prev/next, but never when the bridge's push-on-
# advance poller moves the speaker to the next track on a natural end.
# So the pane goes stale: the speaker plays track N while the pane
# still shows the track the cast started on.
#
# Fix: a client follow-poller. While casting it reads GET /sonos/state
# every few seconds, and when the speaker's current id changes it
# points state.queuePos at the matching queue entry and reflects it.
# It also keeps the play/pause icon honest with the speaker transport.
# Requires the bridge endpoint from sonata_bridge_sonos_state.py.
#
# Three edits, each anchored uniquely:
#   1. Define the poller (startCastPoll / stopCastPoll / castPollOnce)
#      right after reflectCastTrack.
#   2. Start it when a cast begins (in playSonos).
#   3. Stop it when a cast ends (in stopSonos).
#
# Idempotent, timestamped backup, fails loud on a missing or non-unique
# anchor. Run from the repo root:
#   python scripts\sonata_cast_follow.py
# ------------------------------------------------------------------

import sys
import shutil
import datetime
from pathlib import Path

HTML = Path('sonata-pwa.html')
MARKER = 'sonata-sonos-followpoll'

# 1. Poller, inserted after reflectCastTrack's closing brace.
REFLECT_ANCHOR = (
    "function reflectCastTrack(track) {\n"
    "  if (!track) return;\n"
    "  state.currentTrack = track;\n"
    "  state.playing = true;\n"
    "  updateAllPlayerUIs();\n"
    "  renderPlayingState();\n"
    "}\n"
)
POLLER = (
    "\n"
    "/* sonata-sonos-followpoll */\n"
    "// While casting, the bridge's push-on-advance poller moves the\n"
    "// speaker through the queue on its own when a track ends. The\n"
    "// client cannot know unless it asks, so this follows the speaker:\n"
    "// it reads the bridge's current id every few seconds and, when it\n"
    "// changes, points the local display at the matching queue entry.\n"
    "// Manual prev/next update the display directly; this covers the\n"
    "// autonomous advance that previously left the pane stale.\n"
    "let _castPollTimer = null;\n"
    "let _castLastId = null;\n"
    "\n"
    "function startCastPoll() {\n"
    "  _castLastId = (state.currentTrack && (state.currentTrack.jellyfinId || state.currentTrack.id)) || null;\n"
    "  if (_castPollTimer) return;\n"
    "  _castPollTimer = setInterval(castPollOnce, 3000);\n"
    "}\n"
    "\n"
    "function stopCastPoll() {\n"
    "  if (_castPollTimer) { clearInterval(_castPollTimer); _castPollTimer = null; }\n"
    "  _castLastId = null;\n"
    "}\n"
    "\n"
    "async function castPollOnce() {\n"
    "  if (!isCasting()) { stopCastPoll(); return; }\n"
    "  let data;\n"
    "  try {\n"
    "    data = await bridgeGet('/sonos/state?host=' + encodeURIComponent(speaker.activeRoom.id));\n"
    "  } catch (e) { return; } // bridge or speaker hiccup; retry next tick\n"
    "  if (!data) return;\n"
    "\n"
    "  // Keep the play/pause icon honest with the speaker transport.\n"
    "  if (data.transport) {\n"
    "    const playing = data.transport === 'PLAYING' || data.transport === 'TRANSITIONING';\n"
    "    if (playing !== speaker.sonosPlaying) {\n"
    "      speaker.sonosPlaying = playing;\n"
    "      state.playing = playing;\n"
    "      renderPlayingState();\n"
    "    }\n"
    "  }\n"
    "\n"
    "  const id = data.currentId;\n"
    "  if (!id || id === _castLastId) return;\n"
    "  _castLastId = id;\n"
    "\n"
    "  // Follow the speaker: map its current id back to our queue.\n"
    "  if (Array.isArray(state.queue) && state._queueTracks) {\n"
    "    const pos = state.queue.findIndex(i => {\n"
    "      const t = state._queueTracks[i];\n"
    "      return t && (t.jellyfinId || t.id) === id;\n"
    "    });\n"
    "    if (pos >= 0) {\n"
    "      state.queuePos = pos;\n"
    "      reflectCastTrack(state._queueTracks[state.queue[pos]]);\n"
    "      return;\n"
    "    }\n"
    "  }\n"
    "  if (state.currentTrack && (state.currentTrack.jellyfinId || state.currentTrack.id) === id) {\n"
    "    reflectCastTrack(state.currentTrack);\n"
    "  }\n"
    "}\n"
)

# 2. Start the poller when a cast begins (playSonos).
START_ANCHOR = (
    "    setCastIndicator(true);\n"
    "    reflectCastTrack(state.currentTrack);\n"
)
START_REPLACE = (
    "    setCastIndicator(true);\n"
    "    reflectCastTrack(state.currentTrack);\n"
    "    startCastPoll();\n"
)

# 3. Stop the poller when a cast ends (stopSonos).
STOP_ANCHOR = (
    "  setCastIndicator(false);\n"
    "  state.playing = false;\n"
)
STOP_REPLACE = (
    "  setCastIndicator(false);\n"
    "  stopCastPoll();\n"
    "  state.playing = false;\n"
)


def die(msg):
    print('ABORT: ' + msg)
    sys.exit(1)


def apply_once(src, anchor, replace, label):
    n = src.count(anchor)
    if n == 0:
        die(f'{label} anchor not found.')
    if n > 1:
        die(f'{label} anchor not unique ({n} matches).')
    return src.replace(anchor, replace, 1)


def main():
    if not HTML.exists():
        die(f'{HTML} not found. Run from the repo root.')
    src = HTML.read_text(encoding='utf-8')

    if MARKER in src:
        print('Already applied (marker present). Nothing to do.')
        return

    src = apply_once(src, REFLECT_ANCHOR, REFLECT_ANCHOR + POLLER, 'reflectCastTrack')
    src = apply_once(src, START_ANCHOR, START_REPLACE, 'playSonos start')
    src = apply_once(src, STOP_ANCHOR, STOP_REPLACE, 'stopSonos stop')

    if MARKER not in src or 'function castPollOnce' not in src:
        die('post-patch sanity check failed; not writing.')

    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = HTML.with_suffix(f'.backup-{ts}.html')
    shutil.copy2(HTML, backup)
    HTML.write_text(src, encoding='utf-8')
    print(f'Patched {HTML} (backup: {backup.name}).')
    print('Added cast follow-poller, wired into playSonos and stopSonos.')


if __name__ == '__main__':
    main()
