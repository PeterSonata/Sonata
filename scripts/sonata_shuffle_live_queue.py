#!/usr/bin/env python3
"""
sonata_shuffle_live_queue.py

Makes the shuffle button reorder the queue that is already playing.

Before
------
toggleShuffle() flipped state.shuffle and the button highlight but never touched
the live queue. playTracksAt() reads state.shuffle only when playback starts, so
pressing shuffle partway through a playlist did nothing and tracks carried on in
order.

After
-----
Toggling shuffle reorders the current queue immediately:
  - On: the track now playing stays put, every other track in the queue is
    Fisher-Yates shuffled behind it.
  - Off: the queue reverts to natural order, with queuePos moved to wherever the
    current track sits in that order.
If nothing is playing it is a no-op, and the next playTracksAt() honours the flag
as before.

Convention
----------
Idempotent (marker check), timestamped backup, loud failure on a missing or
non-unique anchor. Anchor strings use \\n. Run from the repo root.
"""

import sys
import time
from pathlib import Path

TARGET = Path("sonata-pwa.html")
MARKER = "// applyShuffleToQueue built by sonata_shuffle_live_queue.py"

ANCHOR = (
    "function toggleShuffle() {\n"
    "  state.shuffle = !state.shuffle;\n"
    "  ['shuffle-btn','fp-shuffle-btn'].forEach(id => document.getElementById(id).classList.toggle('active', state.shuffle));\n"
    "}\n"
)

REPLACEMENT = (
    MARKER + "\n"
    "function applyShuffleToQueue() {\n"
    "  // Re-order the live queue when shuffle is toggled mid-playback. Without\n"
    "  // this, toggling only set a flag that the next playTracksAt would read, so\n"
    "  // tracks already playing carried on in order.\n"
    "  if (!state._queueTracks || !state.queue || !state.queue.length) return;\n"
    "  const currentIdx = state.queue[state.queuePos];   // index into _queueTracks\n"
    "  if (state.shuffle) {\n"
    "    const arr = state._queueTracks.map((_, i) => i);\n"
    "    for (let i = arr.length - 1; i > 0; i--) {\n"
    "      const j = Math.floor(Math.random() * (i + 1));\n"
    "      [arr[i], arr[j]] = [arr[j], arr[i]];\n"
    "    }\n"
    "    if (currentIdx != null) {\n"
    "      const pos = arr.indexOf(currentIdx);\n"
    "      if (pos >= 0) { arr.splice(pos, 1); arr.unshift(currentIdx); }\n"
    "    }\n"
    "    state.queue = arr;\n"
    "    state.queuePos = 0;\n"
    "  } else {\n"
    "    state.queue = state._queueTracks.map((_, i) => i);\n"
    "    state.queuePos = currentIdx != null ? currentIdx : 0;\n"
    "  }\n"
    "}\n"
    "\n"
    "function toggleShuffle() {\n"
    "  state.shuffle = !state.shuffle;\n"
    "  ['shuffle-btn','fp-shuffle-btn'].forEach(id => document.getElementById(id).classList.toggle('active', state.shuffle));\n"
    "  applyShuffleToQueue();\n"
    "}\n"
)


def fail(msg):
    print("FAILED: " + msg)
    sys.exit(1)


def main():
    if not TARGET.exists():
        fail(f"{TARGET} not found. Run from the repo root.")

    src = TARGET.read_text(encoding="utf-8")

    if MARKER in src:
        print("Already patched (marker present). Nothing to do.")
        return

    n = src.count(ANCHOR)
    if n == 0:
        fail("toggleShuffle anchor not found (it may have already been edited).")
    if n > 1:
        fail(f"toggleShuffle anchor not unique ({n} occurrences).")

    backup = TARGET.with_suffix(f".backup-{time.strftime('%Y%m%d-%H%M%S')}.html")
    backup.write_text(src, encoding="utf-8")

    patched = src.replace(ANCHOR, REPLACEMENT, 1)
    TARGET.write_text(patched, encoding="utf-8")

    print(f"Patched {TARGET}")
    print(f"Backup written to {backup.name}")
    print("Shuffle now reorders the playing queue. Start a playlist, then tap shuffle.")


if __name__ == "__main__":
    main()
