#!/usr/bin/env python3
# scripts/sonata_sonos_banner.py
# ============================================================
# Fixes the "Casting to <room>" banner never appearing.
#
# reflectCastTrack set the banner by appending to the artist line
# AFTER calling updateAllPlayerUIs(). But other UI refreshes (e.g.
# audio.onpause firing from the audio.pause() in playSonos) call
# updateAllPlayerUIs() again afterward and rewrite the artist line
# to the plain artist, erasing the banner. A race the banner loses.
#
# Fix: compute the cast suffix at write time. A helper castArtist(t)
# returns "Artist · Casting to Room" when casting, else just the
# artist. updateAllPlayerUIs (and the desktop now-playing updater)
# use it for every artist assignment, so any refresh shows the cast
# state instead of racing to overwrite it. The fragile append in
# reflectCastTrack is removed.
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
MARKER = '/* sonata-sonos-banner */'
DEP_MARKER = '/* sonata-sonos-sync */'

# Single-occurrence edits.
EDITS = []

# Add the castArtist helper next to isCasting (anchor on isCasting's
# closing, which the sync patch made a try/catch block).
EDITS.append((
    'add castArtist helper',
    """function isCasting() {
  try { return !!(speaker && speaker.activeRoom); }
  catch (e) { return false; }  // speaker not yet initialised (load-time call)
}""",
    """function isCasting() {
  try { return !!(speaker && speaker.activeRoom); }
  catch (e) { return false; }  // speaker not yet initialised (load-time call)
}
""" + MARKER + """
// Artist label with the cast suffix appended when casting, computed
// at write time so any UI refresh shows it (rather than appending
// after updateAllPlayerUIs, which other refreshes would overwrite).
function castArtist(t) {
  const base = (t && t.artist) || '';
  if (isCasting()) {
    const room = (speaker.activeRoom && speaker.activeRoom.name) || 'speaker';
    return base ? `${base} · Casting to ${room}` : `Casting to ${room}`;
  }
  return base;
}"""
))

# Remove the racing append block from reflectCastTrack.
EDITS.append((
    'remove racing banner append from reflectCastTrack',
    """  updateAllPlayerUIs();
  renderPlayingState();
  // Re-apply the banner: updateAllPlayerUIs has just set the artist
  // line to the real artist, so append the cast label after it.
  const room = (speaker.activeRoom && speaker.activeRoom.name) || 'speaker';
  ['np-artist','mini-artist','fp-artist'].forEach(id => {
    const el = document.getElementById(id);
    if (el && track.artist) el.textContent = `${track.artist} · Casting to ${room}`;
    else if (el) el.textContent = `Casting to ${room}`;
  });
}""",
    """  updateAllPlayerUIs();
  renderPlayingState();
}"""
))

# np-artist and mini-artist assignments are unique by their preceding
# title line, so anchor on the pair.
EDITS.append((
    'np-artist uses castArtist',
    """  document.getElementById('np-title').textContent  = t.title;
  document.getElementById('np-artist').textContent = t.artist;""",
    """  document.getElementById('np-title').textContent  = t.title;
  document.getElementById('np-artist').textContent = castArtist(t);"""
))

EDITS.append((
    'mini-artist uses castArtist',
    """  document.getElementById('mini-title').textContent  = t.title;
  document.getElementById('mini-artist').textContent = t.artist;""",
    """  document.getElementById('mini-title').textContent  = t.title;
  document.getElementById('mini-artist').textContent = castArtist(t);"""
))

# The fp-title + fp-artist pair appears TWICE (updateDesktopNowPlaying
# and updateAllPlayerUIs) with identical text. Both should become
# cast-aware, so replace all occurrences. Handled separately below.
FP_OLD = """  document.getElementById('fp-title').textContent  = t.title;
  document.getElementById('fp-artist').textContent = t.artist;"""
FP_NEW = """  document.getElementById('fp-title').textContent  = t.title;
  document.getElementById('fp-artist').textContent = castArtist(t);"""


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

    # Single-occurrence anchors.
    for desc, old, _new in EDITS:
        n = text.count(old)
        if n == 0:
            fail(f"anchor not found for: {desc}")
        if n > 1:
            fail(f"anchor not unique ({n} matches) for: {desc}")

    # The fp pair must appear exactly twice (two functions).
    fp_count = text.count(FP_OLD)
    if fp_count != 2:
        fail(f"expected the fp-title/fp-artist pair exactly twice, found {fp_count}")

    new_text = text
    for _desc, old, new in EDITS:
        new_text = new_text.replace(old, new, 1)
    # Replace both fp occurrences.
    new_text = new_text.replace(FP_OLD, FP_NEW)

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = HTML.with_suffix(f'.backup-{stamp}.html')
    backup.write_text(text, encoding='utf-8')
    print(f"Backup written: {backup}")

    HTML.write_text(new_text, encoding='utf-8')
    print("Cast banner now shown via castArtist at write time.")
    print("Deploy: commit, push, hard-reload desktop (Ctrl+F5).")


if __name__ == '__main__':
    main()
