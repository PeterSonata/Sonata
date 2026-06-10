#!/usr/bin/env python3
# sonata_sonos_output_sink.py
# ------------------------------------------------------------------
# Makes Sonos casting a persistent output sink rather than a one-shot
# tied to the track that started the cast.
#
# Problem: playTracksAt -> playCurrentQueue is the single entry point
# for all new playback in the main app, and it always loaded local
# audio with no cast awareness. The cast redirect added previously only
# guarded togglePlay / prevTrack / nextTrack (the transport bar), so
# starting a NEW album while casting played it on the PC speakers and
# left the Sonos on the old track.
#
# Fix: guard playCurrentQueue. When a room is active, send the current
# queue to the speaker instead of loading local audio. Every play path
# (album play-all, track row click, search, genre, jukebox) funnels
# through playCurrentQueue, so all of them now follow the cast. When not
# casting, isCasting() is false and the function behaves exactly as
# before, so there is no regression. isCasting() is load-safe (it
# try/catches the late-declared speaker const), so the guard is safe
# even on an early call.
#
# Two edits:
#   1. Insert a cast guard at the top of playCurrentQueue.
#   2. Define castCurrentQueue() next to the cast layer (before playSonos),
#      reusing the existing sonosQueueIds, bridgePost, setCastIndicator
#      and reflectCastTrack helpers.
#
# Idempotent, timestamped backup, fails loud on a missing or non-unique
# anchor, aborts before writing if the sanity check fails. Run from the
# repo root: python scripts\sonata_sonos_output_sink.py
# ------------------------------------------------------------------

import sys
import shutil
import datetime
from pathlib import Path

HTML = Path('sonata-pwa.html')
MARKER = 'sonata-sonos-output-sink'

GUARD_ANCHOR = (
    "function playCurrentQueue() {\n"
    "  if (state.queuePos < 0 || state.queuePos >= state.queue.length) return;\n"
)
GUARD_INSERT = (
    "  /* sonata-sonos-output-sink: a live cast is a persistent output;\n"
    "     route any new playback to the active room, not the local audio. */\n"
    "  if (isCasting()) { castCurrentQueue(); return; }\n"
)

FUNC_ANCHOR = "async function playSonos(room) {\n"
FUNC_INSERT = (
    "// sonata-sonos-output-sink\n"
    "// Send the current queue (from queuePos onward) to the active Sonos\n"
    "// room and reflect it in the display, without touching local audio.\n"
    "// Called from playCurrentQueue whenever new playback begins while a\n"
    "// room is active, so casting behaves as a persistent output for\n"
    "// everything Sonata plays, not just the track that started the cast.\n"
    "async function castCurrentQueue() {\n"
    "  const room = speaker.activeRoom;\n"
    "  if (!room) return;\n"
    "  const t = (state._queueTracks && state.queue && state.queue.length)\n"
    "    ? state._queueTracks[state.queue[state.queuePos]]\n"
    "    : state.currentTrack;\n"
    "  // We are an output sink now: keep local audio silent.\n"
    "  try { audio.pause(); } catch (e) {}\n"
    "  const ids = sonosQueueIds();\n"
    "  if (!ids.length) { showToast('Nothing to cast'); return; }\n"
    "  try {\n"
    "    await bridgePost('/sonos/play', { host: room.id, ids });\n"
    "    speaker.sonosPlaying = true;\n"
    "    setCastIndicator(true);\n"
    "    if (t) reflectCastTrack(t); else updateAllPlayerUIs();\n"
    "  } catch (e) {\n"
    "    showToast('Sonos play failed');\n"
    "  }\n"
    "}\n\n"
)


def die(msg):
    print('ABORT: ' + msg)
    sys.exit(1)


def insert_once(src, anchor, insert, before, label):
    n = src.count(anchor)
    if n == 0:
        die(f'{label} anchor not found.')
    if n > 1:
        die(f'{label} anchor not unique ({n} matches).')
    repl = (insert + anchor) if before else (anchor + insert)
    return src.replace(anchor, repl, 1)


def main():
    if not HTML.exists():
        die(f'{HTML} not found. Run from the repo root.')
    src = HTML.read_text(encoding='utf-8')

    if MARKER in src:
        print('Already applied (marker present). Nothing to do.')
        return

    src = insert_once(src, GUARD_ANCHOR, GUARD_INSERT, before=False,
                      label='playCurrentQueue')
    src = insert_once(src, FUNC_ANCHOR, FUNC_INSERT, before=True,
                      label='playSonos')

    if MARKER not in src or 'function castCurrentQueue' not in src:
        die('post-patch sanity check failed; not writing.')

    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = HTML.with_suffix(f'.backup-{ts}.html')
    shutil.copy2(HTML, backup)
    HTML.write_text(src, encoding='utf-8')
    print(f'Patched {HTML} (backup: {backup.name}).')
    print('Edits: cast guard in playCurrentQueue, castCurrentQueue() before playSonos.')


if __name__ == '__main__':
    main()
