#!/usr/bin/env python3
"""
patch_desktop_real_pause.py

Fixes the OS media overlay resume button on desktop.

The silent-loop keepalive (an iOS workaround) means the audio element never
actually pauses: on pause it swaps to a looping silent WAV and keeps playing.
Windows derives the overlay's play/pause toggle from the element's real state,
so after a pause it still thinks audio is playing, maps the toggle to "pause"
again, and pressing it calls pausePlayback() which early-returns on _silentMode.
Net effect: pause and next work, resume does nothing.

This patch makes pause and resume operate on the element for real on non-iOS,
where a paused element keeps the media session alive anyway. The iOS path
(silent-loop keepalive) is left untouched. Uses the existing isIOS flag.

Safe to run repeatedly: idempotent on the marker 'sonata-desktop-real-pause'.
Creates a timestamped backup. Fails loudly if any anchor is missing or
ambiguous.

Run from the repo root:
    cd C:\\Users\\peter\\repos\\sonata
    python scripts\\patch_desktop_real_pause.py
"""

import sys
import datetime
from pathlib import Path

TARGET = Path("sonata-pwa.html")
MARKER = "sonata-desktop-real-pause"


def die(msg):
    print("ABORT: " + msg)
    sys.exit(1)


def apply(text, old, new, label):
    n = text.count(old)
    if n == 0:
        die("anchor not found: " + label)
    if n > 1:
        die("anchor matched %d times (expected exactly 1): %s" % (n, label))
    return text.replace(old, new)


def main():
    if not TARGET.exists():
        die("%s not found. Run from the repo root." % TARGET)

    text = TARGET.read_text(encoding="utf-8")  # CRLF -> LF in memory on Windows

    if MARKER in text:
        print("Already patched (marker present). Nothing to do.")
        return

    if "const isIOS" not in text:
        die("isIOS flag not found; expected an existing platform check.")

    # ---- 1. Real pause on desktop ----
    pause_old = (
        "function pausePlayback() {\n"
        "  if (!state.currentTrack || _silentMode) return;\n"
        "  _savedSrc = audio.src;"
    )
    pause_new = (
        "function pausePlayback() {\n"
        "  if (!state.currentTrack) return;\n"
        "  // " + MARKER + ": desktop browsers keep the media session alive across a\n"
        "  // real pause, so pause the element for real. That keeps the OS overlay's\n"
        "  // play/pause state honest, which is what lets its resume button work. The\n"
        "  // silent-loop keepalive below is only needed on iOS, where the audio\n"
        "  // session is dropped the moment audio goes silent.\n"
        "  if (!isIOS) { audio.pause(); return; }\n"
        "  if (_silentMode) return;\n"
        "  _savedSrc = audio.src;"
    )
    text = apply(text, pause_old, pause_new, "pausePlayback header")

    # ---- 2. Real resume on desktop ----
    resume_old = (
        "function resumePlayback() {\n"
        "  if (!state.currentTrack) return;\n"
        "  if (_silentMode && _savedSrc) {"
    )
    resume_new = (
        "function resumePlayback() {\n"
        "  if (!state.currentTrack) return;\n"
        "  if (!isIOS) { audio.play().catch(() => {}); return; }\n"
        "  if (_silentMode && _savedSrc) {"
    )
    text = apply(text, resume_old, resume_new, "resumePlayback header")

    # ---- backup (exact bytes) + write ----
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = TARGET.with_name(TARGET.name + ".bak-" + stamp)
    backup.write_bytes(TARGET.read_bytes())
    TARGET.write_text(text, encoding="utf-8")  # \n -> CRLF on Windows

    print("Patched %s" % TARGET)
    print("Backup  %s" % backup)


if __name__ == "__main__":
    main()
