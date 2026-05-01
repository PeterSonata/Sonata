#!/usr/bin/env python3
"""
Sonata PWA - iOS background audio fixes
========================================

Fixes two iOS-specific bugs:

  A. Pause + lock: pressing pause on iPhone, then locking the screen,
     prevents the AirPod / lock-screen play button from resuming
     playback. iOS releases the audio session within seconds of audio
     going silent, and only a foreground gesture can re-acquire it.

  B. Track-end advance: when an album track finishes naturally, Sonata
     does not move on to the next track unless the app is in the
     foreground. Same root cause: iOS releases the session in the gap
     between Track A ending and Track B starting.

Both bugs are fixed by the "silent loop" trick: Sonata never lets the
audio element fall silent. Instead of fully pausing or letting a
track end into silence, we swap audio.src to a tiny silent WAV on
loop. iOS sees continuous audio output and keeps the session alive.
When playback resumes (or the next track is ready), we swap back.

USAGE
-----
Run this in the same folder as sonata-pwa.html:

    python sonata_ios_background.py

Default behaviour:
  - Reads:  sonata-pwa.html
  - Writes: sonata-pwa.html (in place)
  - Backs up the original to: sonata-pwa.backup-ios-background.html

Pass a different filename if needed:

    python sonata_ios_background.py my-sonata.html

The patcher is independent of Round 1 and the search performance
patcher. It can be applied before or after either, in any order. Each
anchor is unique enough that ordering does not matter.
"""
from __future__ import annotations
import sys
import shutil
from pathlib import Path


def must_replace(html: str, old: str, new: str, label: str) -> str:
    """Replace `old` with `new` exactly once. Bail loudly otherwise."""
    count = html.count(old)
    if count == 0:
        raise SystemExit(
            f"FAIL [{label}]: anchor not found in source file.\n"
            f"  Expected substring (first 200 chars):\n  {old[:200]!r}"
        )
    if count > 1:
        raise SystemExit(
            f"FAIL [{label}]: anchor found {count} times, must be unique.\n"
            f"  Substring (first 200 chars):\n  {old[:200]!r}"
        )
    return html.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Patch 1: inject silent loop infrastructure and helper functions
# ---------------------------------------------------------------------------

SILENT_LOOP_BLOCK = """
// === iOS background-audio keepalive (silent loop trick) ===
//
// iOS releases the audio session within seconds of <audio> going silent.
// Once released, only a foreground user gesture can re-acquire it - so
// the lock-screen play button stops working after a pause, and tracks
// don't advance when one ends. To prevent this we never let audio fall
// silent: when "pausing" or transitioning between tracks, we swap to a
// tiny silent WAV on loop. iOS keeps the session alive, and lock-screen
// controls keep working.

function _makeSilentWav() {
  // 1 second of 8-bit unsigned mono silence at 8 kHz. About 8 KB.
  const sampleRate = 8000;
  const numSamples = sampleRate;
  const buf = new ArrayBuffer(44 + numSamples);
  const v = new DataView(buf);
  // RIFF header
  [0x52,0x49,0x46,0x46].forEach((b,i) => v.setUint8(i, b));        // "RIFF"
  v.setUint32(4, 36 + numSamples, true);
  [0x57,0x41,0x56,0x45].forEach((b,i) => v.setUint8(8+i, b));      // "WAVE"
  [0x66,0x6d,0x74,0x20].forEach((b,i) => v.setUint8(12+i, b));     // "fmt "
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);                                        // PCM
  v.setUint16(22, 1, true);                                        // mono
  v.setUint32(24, sampleRate, true);
  v.setUint32(28, sampleRate, true);
  v.setUint16(32, 1, true);
  v.setUint16(34, 8, true);                                        // 8-bit
  [0x64,0x61,0x74,0x61].forEach((b,i) => v.setUint8(36+i, b));     // "data"
  v.setUint32(40, numSamples, true);
  // 8-bit unsigned PCM uses 0x80 as silence (midpoint)
  for (let i = 0; i < numSamples; i++) v.setUint8(44+i, 0x80);
  return URL.createObjectURL(new Blob([buf], { type: 'audio/wav' }));
}

const SILENT_LOOP_URL = _makeSilentWav();
let _silentMode = false;
let _savedSrc = null;
let _savedTime = 0;

function isSilent() { return _silentMode; }

// Swap to silent loop. Used for pause and as a bridge during track
// transitions. Audio session stays alive because audio is technically
// still playing (silently).
function pausePlayback() {
  if (!state.currentTrack || _silentMode) return;
  _savedSrc = audio.src;
  _savedTime = audio.currentTime;
  _silentMode = true;
  audio.loop = true;
  audio.src = SILENT_LOOP_URL;
  audio.play().catch(() => {});
  // The src swap won't fire a clean onpause for the real track, so
  // update state directly.
  state.playing = false;
  updateAllPlayerUIs();
  renderPlayingState();
  updateMediaSession();
}

function resumePlayback() {
  if (!state.currentTrack) return;
  if (_silentMode && _savedSrc) {
    const restoreTime = _savedTime;
    const restoreSrc = _savedSrc;
    _silentMode = false;
    _savedSrc = null;
    audio.loop = false;
    audio.src = restoreSrc;
    // Restore position once the real track's metadata loads.
    audio.addEventListener('loadedmetadata', () => {
      try { audio.currentTime = restoreTime; } catch (e) {}
    }, { once: true });
  }
  audio.play().catch(() => {});
  // onplay fires when real audio starts; it will update UI and
  // mediaSession via the existing audio.onplay handler.
}

// Bridge through silent loop while loading the next track. Used by
// onended so iOS doesn't release the session in the gap between the
// finishing track and the next one starting.
function _bridgeAndAdvance() {
  _silentMode = true;
  audio.loop = true;
  audio.src = SILENT_LOOP_URL;
  audio.play().catch(() => {});
  // Give the silent loop a brief moment to actually start producing
  // sound before we change src to the next track.
  setTimeout(() => {
    _silentMode = false;
    audio.loop = false;
    playCurrentQueue();
    renderView();
  }, 120);
}

"""

def patch_inject_helpers(html: str) -> str:
    return must_replace(
        html,
        "const audio = document.getElementById('audio');\n"
        "audio.volume = state.volume;\n"
        "\n"
        "function playTracksAt(tracks, idx) {",
        "const audio = document.getElementById('audio');\n"
        "audio.volume = state.volume;\n"
        + SILENT_LOOP_BLOCK +
        "function playTracksAt(tracks, idx) {",
        'inject-helpers',
    )


# ---------------------------------------------------------------------------
# Patch 2: ontimeupdate ignores silent loop
# ---------------------------------------------------------------------------

def patch_ontimeupdate(html: str) -> str:
    return must_replace(
        html,
        "audio.ontimeupdate = () => {\n"
        "  if (!audio.duration) return;\n",
        "audio.ontimeupdate = () => {\n"
        "  if (_silentMode) return;   // ignore ticks from silent loop\n"
        "  if (!audio.duration) return;\n",
        'ontimeupdate-silent-skip',
    )


# ---------------------------------------------------------------------------
# Patch 3: onended bridges through silent loop
# ---------------------------------------------------------------------------

def patch_onended(html: str) -> str:
    return must_replace(
        html,
        "audio.onended = () => {\n"
        "  if (state.repeat === 'one') { audio.play(); return; }\n"
        "  state.queuePos++;\n"
        "  if (state.queuePos >= state.queue.length) {\n"
        "    if (state.repeat === 'all') state.queuePos = 0;\n"
        "    else { state.playing = false; updateAllPlayerUIs(); return; }\n"
        "  }\n"
        "  playCurrentQueue();\n"
        "  renderView();\n"
        "};\n",
        "audio.onended = () => {\n"
        "  if (_silentMode) return;   // silent loop has loop=true so this shouldn't fire, but guard anyway\n"
        "  if (state.repeat === 'one') { audio.play(); return; }\n"
        "  state.queuePos++;\n"
        "  if (state.queuePos >= state.queue.length) {\n"
        "    if (state.repeat === 'all') state.queuePos = 0;\n"
        "    else { state.playing = false; updateAllPlayerUIs(); return; }\n"
        "  }\n"
        "  // Bridge through silent loop so iOS keeps the audio session\n"
        "  // alive while the next track loads.\n"
        "  _bridgeAndAdvance();\n"
        "};\n",
        'onended-bridge',
    )


# ---------------------------------------------------------------------------
# Patch 4: onplay / onpause ignore silent loop firings
# ---------------------------------------------------------------------------

def patch_onplay_onpause(html: str) -> str:
    html = must_replace(
        html,
        "audio.onplay  = () => { state.playing = true;  updateAllPlayerUIs(); renderPlayingState(); updateMediaSession(); };\n"
        "audio.onpause = () => { state.playing = false; updateAllPlayerUIs(); renderPlayingState(); updateMediaSession(); };\n",
        "audio.onplay  = () => {\n"
        "  if (_silentMode) return;  // silent loop, not a real play\n"
        "  state.playing = true;  updateAllPlayerUIs(); renderPlayingState(); updateMediaSession();\n"
        "};\n"
        "audio.onpause = () => {\n"
        "  if (_silentMode) return;  // we faked a pause via silent loop\n"
        "  state.playing = false; updateAllPlayerUIs(); renderPlayingState(); updateMediaSession();\n"
        "};\n",
        'onplay-onpause-silent-skip',
    )
    return html


# ---------------------------------------------------------------------------
# Patch 5: togglePlay uses pausePlayback / resumePlayback
# ---------------------------------------------------------------------------

def patch_toggle_play(html: str) -> str:
    return must_replace(
        html,
        "function togglePlay() {\n"
        "  if (!state.currentTrack) return;\n"
        "  state.playing ? audio.pause() : audio.play();\n"
        "}\n",
        "function togglePlay() {\n"
        "  if (!state.currentTrack) return;\n"
        "  state.playing ? pausePlayback() : resumePlayback();\n"
        "}\n",
        'togglePlay',
    )


# ---------------------------------------------------------------------------
# Patch 6: Media Session play / pause action handlers
# ---------------------------------------------------------------------------

def patch_media_session(html: str) -> str:
    return must_replace(
        html,
        "  navigator.mediaSession.setActionHandler('play',         () => audio.play());\n"
        "  navigator.mediaSession.setActionHandler('pause',        () => audio.pause());\n",
        "  navigator.mediaSession.setActionHandler('play',         () => resumePlayback());\n"
        "  navigator.mediaSession.setActionHandler('pause',        () => pausePlayback());\n",
        'mediaSession-handlers',
    )


# ---------------------------------------------------------------------------
# Patch 7: playCurrentQueue clears silent mode (defensive)
# ---------------------------------------------------------------------------

def patch_playCurrentQueue(html: str) -> str:
    # When a fresh track is loaded via playCurrentQueue, we should never be
    # in silent mode afterwards. Clear it defensively at the top.
    return must_replace(
        html,
        "function playCurrentQueue() {\n"
        "  if (state.queuePos < 0 || state.queuePos >= state.queue.length) return;\n",
        "function playCurrentQueue() {\n"
        "  if (state.queuePos < 0 || state.queuePos >= state.queue.length) return;\n"
        "  // Defensive: any new-track load clears silent-loop state.\n"
        "  _silentMode = false; _savedSrc = null; audio.loop = false;\n",
        'playCurrentQueue-clear-silent',
    )


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def main() -> None:
    src_path = Path(sys.argv[1] if len(sys.argv) > 1 else 'sonata-pwa.html')
    if not src_path.exists():
        raise SystemExit(f"Source file not found: {src_path}")

    backup_path = src_path.with_name(src_path.stem + '.backup-ios-background.html')
    shutil.copy(src_path, backup_path)
    print(f"[backup] {backup_path}")

    html = src_path.read_text(encoding='utf-8')
    print(f"[input ] {len(html):,} bytes")

    html = patch_inject_helpers(html)
    html = patch_ontimeupdate(html)
    html = patch_onended(html)
    html = patch_onplay_onpause(html)
    html = patch_toggle_play(html)
    html = patch_media_session(html)
    html = patch_playCurrentQueue(html)

    src_path.write_text(html, encoding='utf-8')
    print(f"[output] {len(html):,} bytes -> {src_path}")
    print()
    print("iOS background-audio patch complete.")
    print("Reload Sonata (force-refresh) and verify on iPhone PWA:")
    print("  1. Play a track. Lock screen. Pause via lock screen. Press play.")
    print("     -> Should resume playback.")
    print("  2. Play a track. Let it play to the end while screen is locked.")
    print("     -> Next track should start automatically.")
    print()
    print("If anything is broken, restore from the backup file above.")


if __name__ == '__main__':
    main()
