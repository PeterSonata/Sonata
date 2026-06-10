#!/usr/bin/env python3
"""
patch_mediasession_rich.py

Enriches Sonata's existing Media Session integration so the OS media
overlay (Windows media flyout, lock screen, hardware media keys) shows
album artwork and an accurate progress bar.

What it does:
  1. Adds an artwork array to MediaMetadata, derived from the track's
     Jellyfin Primary-image URL, at three sizes so the shell can pick
     whichever fits the surface. Without this the flyout shows a blank
     thumbnail.
  2. Adds setPositionState so the OS scrubber tracks real playback
     position and duration. Pushed on every state change, plus a
     throttled tick (~1/sec) from ontimeupdate.

Safe to run repeatedly: idempotent on the marker 'sonata-mediasession-rich'.
Creates a timestamped backup. Fails loudly if any anchor is missing or
ambiguous.

Run from the repo root:
    cd C:\\Users\\peter\\repos\\sonata
    python scripts\\patch_mediasession_rich.py
"""

import sys
import datetime
from pathlib import Path

TARGET = Path("sonata-pwa.html")
MARKER = "sonata-mediasession-rich"


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

    # ---- 1. Inject helpers immediately before updateMediaSession ----
    helpers = (
        "// " + MARKER + ": artwork + position state for the OS media overlay.\n"
        "let _msLastPos = 0;\n"
        "\n"
        "function _msArtwork(t) {\n"
        "  if (!t || !t.artUrl) return [];\n"
        "  // t.artUrl is a Jellyfin Primary-image URL carrying maxHeight=300.\n"
        "  // Offer the shell a few sizes by rewriting the height hint; it picks\n"
        "  // whichever fits the surface (flyout, lock screen, media keys popup).\n"
        "  if (!/maxHeight=\\d+/.test(t.artUrl)) {\n"
        "    return [{ src: t.artUrl, sizes: '300x300' }];\n"
        "  }\n"
        "  const mk = (h) => ({ src: t.artUrl.replace(/maxHeight=\\d+/, 'maxHeight=' + h), sizes: h + 'x' + h });\n"
        "  return [mk(96), mk(256), mk(512)];\n"
        "}\n"
        "\n"
        "function _msSetPosition(force) {\n"
        "  if (!('mediaSession' in navigator) || !('setPositionState' in navigator.mediaSession)) return;\n"
        "  if (_silentMode) return;\n"
        "  const dur = audio.duration;\n"
        "  if (!dur || !isFinite(dur)) return;            // stream not ready, or live: skip\n"
        "  const now = Date.now();\n"
        "  if (!force && now - _msLastPos < 900) return;  // throttle to ~1/sec\n"
        "  _msLastPos = now;\n"
        "  try {\n"
        "    navigator.mediaSession.setPositionState({\n"
        "      duration: dur,\n"
        "      playbackRate: audio.playbackRate || 1,\n"
        "      position: Math.min(audio.currentTime || 0, dur),\n"
        "    });\n"
        "  } catch (e) { /* invalid values, ignore */ }\n"
        "}\n"
        "\n"
        "function updateMediaSession() {"
    )
    text = apply(text, "function updateMediaSession() {", helpers,
                 "updateMediaSession definition")

    # ---- 2. Add artwork to the MediaMetadata ----
    meta_old = (
        "    title:  t.title,\n"
        "    artist: t.artist,\n"
        "    album:  t.album,\n"
        "  });"
    )
    meta_new = (
        "    title:  t.title,\n"
        "    artist: t.artist,\n"
        "    album:  t.album,\n"
        "    artwork: _msArtwork(t),\n"
        "  });"
    )
    text = apply(text, meta_old, meta_new, "MediaMetadata artwork")

    # ---- 3. Push an accurate position on every state change ----
    pb_old = (
        "  navigator.mediaSession.playbackState = state.playing ? 'playing' : 'paused';\n"
        "}"
    )
    pb_new = (
        "  navigator.mediaSession.playbackState = state.playing ? 'playing' : 'paused';\n"
        "  _msSetPosition(true);\n"
        "}"
    )
    text = apply(text, pb_old, pb_new, "playbackState position push")

    # ---- 4. Track position during playback (throttled) ----
    tu_old = (
        "audio.ontimeupdate = () => {\n"
        "  if (_silentMode) return;   // ignore ticks from silent loop\n"
        "  if (!audio.duration) return;"
    )
    tu_new = (
        "audio.ontimeupdate = () => {\n"
        "  if (_silentMode) return;   // ignore ticks from silent loop\n"
        "  if (!audio.duration) return;\n"
        "  _msSetPosition();"
    )
    text = apply(text, tu_old, tu_new, "ontimeupdate position tick")

    # ---- backup (exact bytes) + write ----
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = TARGET.with_name(TARGET.name + ".bak-" + stamp)
    backup.write_bytes(TARGET.read_bytes())
    TARGET.write_text(text, encoding="utf-8")  # \n -> CRLF on Windows

    print("Patched %s" % TARGET)
    print("Backup  %s" % backup)


if __name__ == "__main__":
    main()
