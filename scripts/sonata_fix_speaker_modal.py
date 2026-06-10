#!/usr/bin/env python3
# scripts/sonata_fix_speaker_modal.py
# ============================================================
# Fixes a pre-existing crash that stopped the cast/speaker modal
# from ever opening.
#
# Symptom: clicking the cast icon did nothing, on desktop and
# iPhone. No modal appeared.
#
# Cause: openSpeakerModal() calls loadSonosBridgeUrl() as its first
# line. That function tries to set .value on getElementById(
# 'sonos-bridge-input'), but that input was removed from the
# settings markup in an earlier revision. getElementById returns
# null, so `.value = ...` throws "Cannot set properties of null",
# which aborts openSpeakerModal before it shows the modal.
#
# loadSonosBridgeUrl is obsolete: the separate sonos-bridge-URL
# concept was superseded by the shared nas.activeURL connection.
# Discovery now runs through that. So this:
#   - rewrites openSpeakerModal to drop the loadSonosBridgeUrl call
#     and kick discoverSonosRooms() directly (so rooms populate when
#     the modal opens, via the live NAS connection)
#   - neutralises loadSonosBridgeUrl to a safe no-op, in case any
#     other path calls it
#
# Conventions: run from repo root, idempotent, timestamped backup,
# fails loud on missing/non-unique anchors, LF anchors.
# ============================================================

import sys
from datetime import datetime
from pathlib import Path

HTML = Path('sonata-pwa.html')
MARKER = '/* sonata-speaker-modal-fixed */'

EDITS = [
    (
        'openSpeakerModal drops loadSonosBridgeUrl, kicks discovery',
        """function openSpeakerModal() {
  loadSonosBridgeUrl();
  renderSpeakerModal();
  document.getElementById('speaker-modal').classList.add('visible');
}""",
        """function openSpeakerModal() {
  """ + MARKER + """
  renderSpeakerModal();
  document.getElementById('speaker-modal').classList.add('visible');
  // Discover rooms through the live NAS connection. Replaces the old
  // loadSonosBridgeUrl() path, which referenced a settings input that
  // no longer exists and threw before the modal could show.
  discoverSonosRooms();
}""",
    ),
    (
        'loadSonosBridgeUrl neutralised to a safe no-op',
        """function loadSonosBridgeUrl() {
  const saved = localStorage.getItem('sonata_sonos_bridge') || '';
  document.getElementById('sonos-bridge-input').value = saved;
  speaker.sonosBridgeUrl = saved;
  if (saved) discoverSonosRooms();
}""",
        """function loadSonosBridgeUrl() {
  // Obsolete: the separate Sonos bridge URL was replaced by the
  // shared nas.activeURL connection. Kept as a no-op so any stray
  // caller cannot throw. Discovery is kicked from openSpeakerModal.
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
        print("Already fixed (marker present). Nothing to do.")
        return

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
    print("Fixed the speaker modal crash.")
    for desc, _o, _n in EDITS:
        print(f"  - {desc}")
    print("Deploy: commit, push, hard-reload desktop (Ctrl+F5).")


if __name__ == '__main__':
    main()
