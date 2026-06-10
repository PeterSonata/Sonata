#!/usr/bin/env python3
# scripts/sonata_sonos_playstate.py
# ============================================================
# Fixes the play/pause icon getting stuck while casting.
#
# togglePlay's cast branch toggled speaker.sonosPlaying and called
# updateAllPlayerUIs(), but that function reads state.playing (not
# speaker.sonosPlaying) to pick the play vs pause icon. The two were
# never synced, so the icon froze on "pause" and never flipped back
# when you paused the speaker.
#
# Fix: in the cast branch, set state.playing to match
# speaker.sonosPlaying before updating the UI, so the icon tracks
# the speaker's actual play state.
#
# Depends on the sync patch (marker sonata-sonos-sync).
#
# Conventions: run from repo root, idempotent, timestamped backup,
# fails loud on missing/non-unique anchors, LF anchors.
# ============================================================

import sys
from datetime import datetime
from pathlib import Path

HTML = Path('sonata-pwa.html')
MARKER = '/* sonata-sonos-playstate */'
DEP_MARKER = '/* sonata-sonos-sync */'

EDITS = [
    (
        'togglePlay cast branch syncs state.playing to the speaker',
        """  if (isCasting()) {
    if (speaker.sonosPlaying) { sonosControl('/sonos/pause'); speaker.sonosPlaying = false; }
    else { sonosControl('/sonos/resume'); speaker.sonosPlaying = true; }
    updateAllPlayerUIs();
    return;
  }""",
        """  if (isCasting()) {
    """ + MARKER + """
    if (speaker.sonosPlaying) { sonosControl('/sonos/pause'); speaker.sonosPlaying = false; }
    else { sonosControl('/sonos/resume'); speaker.sonosPlaying = true; }
    // Keep state.playing in step so updateAllPlayerUIs picks the right
    // icon (it reads state.playing, not speaker.sonosPlaying).
    state.playing = speaker.sonosPlaying;
    updateAllPlayerUIs();
    return;
  }""",
    ),
]


def fail(msg):
    print(f"ABORT: {msg}")
    sys.exit(1)


def main():
    if not HTML.exists():
        fail(f"{HTML} not found. Run from the repo root.")

    text = HTML.read_text(encoding='utf-8')

    if MARKER in text:
        print("Already applied (marker present). Nothing to do.")
        return

    if DEP_MARKER not in text:
        fail("dependency missing: the sync patch (sonata_sonos_sync.py) "
             "must be applied first.")

    for desc, old, _new in EDITS:
        n = text.count(old)
        if n == 0:
            fail(f"anchor not found for: {desc}")
        if n > 1:
            fail(f"anchor not unique ({n} matches) for: {desc}")

    new_text = text
    for _desc, old, new in EDITS:
        new_text = new_text.replace(old, new, 1)

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = HTML.with_suffix(f'.backup-{stamp}.html')
    backup.write_text(text, encoding='utf-8')
    print(f"Backup written: {backup}")

    HTML.write_text(new_text, encoding='utf-8')
    print("Fixed play/pause icon sync while casting.")
    print("Deploy: commit, push, hard-reload desktop (Ctrl+F5).")


if __name__ == '__main__':
    main()
