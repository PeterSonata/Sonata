#!/usr/bin/env python3
"""
sonata_home_picks_coldstart.py

Fixes the cold-start bug where the home screen shows only OPFS-saved albums
instead of the day's 12 picks.

Background
----------
The INIT sequence runs loadSavedTracks() and renders home BEFORE the library
cache has loaded, so state.tracks holds only the saved tracks. At that moment
ensureHomePicks() validates today's stored picks against the saved-only index,
drops everything that does not resolve, tops up from a shuffle that can only
produce the same saved albums, and PERSISTS the result to localStorage as
today's picks. When the full library arrives moments later, ensureHomePicks()
sees valid stored picks for today and keeps them. The corruption sticks until
midnight (or a manual Reshuffle).

Fix
---
1. Add state.libraryReady and state.homePicksProvisional flags.
2. Guard ensureHomePicks(): before the library is ready, show today's stored
   picks verbatim (pick objects carry seed/artUrl so they render without
   tracks), or a provisional shuffle if none, and never validate, top up or
   write to storage. Once ready, discard the provisional in-memory copy so
   picks re-derive against the full index.
3. Set state.libraryReady = true in INIT after loadCachedLibrary() succeeds,
   and after the first-run bridge sync / Jellyfin walk completes.

Already-corrupted stored picks self-heal: the valid entries are kept and the
set is topped back up to 12 from the full library.

Convention
----------
Idempotent (marker check), timestamped backup, loud failure on a missing or
non-unique anchor. Anchor strings use \\n; CRLF files are handled by
converting anchors and insertions to the file's convention. Run from the
repo root.
"""

import sys
import time
from pathlib import Path

TARGET = Path("sonata-pwa.html")
MARKER = "sonata_home_picks_coldstart.py"

EDITS = [
    # 1. State flags
    (
        "  homeShuffle: null,   // Cached random selection of 12 albums for the home view\n",
        "  homeShuffle: null,   // Cached random selection of 12 albums for the home view\n"
        "  libraryReady: false, // True once the library cache or first-run fetch has loaded (sonata_home_picks_coldstart.py)\n"
        "  homePicksProvisional: false, // True when homeShuffle was set before libraryReady\n",
    ),
    # 2. Guard at the top of ensureHomePicks
    (
        "function ensureHomePicks() {\n"
        "  if (state.homeShuffle && state.homeShuffle.length) {\n",
        "function ensureHomePicks() {\n"
        "  // \u2500\u2500 Cold-start guard (sonata_home_picks_coldstart.py) \u2500\u2500\n"
        "  // Before the library cache has loaded, state.tracks holds only OPFS-saved\n"
        "  // tracks. Validating, topping up or persisting picks against that subset\n"
        "  // clobbers the real daily picks in localStorage. Show today's stored picks\n"
        "  // verbatim (pick objects carry their own seed/artUrl so they render without\n"
        "  // tracks), or a provisional shuffle, and never write to storage until the\n"
        "  // library is fully loaded.\n"
        "  if (!state.libraryReady) {\n"
        "    const storedEarly = loadStoredHomePicks();\n"
        "    state.homeShuffle = (storedEarly && storedEarly.length) ? storedEarly : pickRandomAlbums(12);\n"
        "    state.homePicksProvisional = true;\n"
        "    return;\n"
        "  }\n"
        "  if (state.homePicksProvisional) {\n"
        "    // Library has arrived since the provisional render \u2014 discard and re-derive\n"
        "    state.homeShuffle = null;\n"
        "    state.homePicksProvisional = false;\n"
        "  }\n"
        "  if (state.homeShuffle && state.homeShuffle.length) {\n",
    ),
    # 3. libraryReady on cache-hit boot
    (
        "    const fromCache = await loadCachedLibrary();\n"
        "    if (fromCache) {\n",
        "    const fromCache = await loadCachedLibrary();\n"
        "    if (fromCache) {\n"
        "      state.libraryReady = true;   // sonata_home_picks_coldstart.py\n",
    ),
    # 4. libraryReady on first-run fetch
    (
        "      if (!gotFromBridge) await fetchLibrary({ keepSplash: true });\n",
        "      if (!gotFromBridge) await fetchLibrary({ keepSplash: true });\n"
        "      state.libraryReady = true;   // sonata_home_picks_coldstart.py\n",
    ),
]


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def main():
    if not TARGET.exists():
        fail(f"{TARGET} not found. Run from the repo root.")

    with open(TARGET, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    if MARKER in src:
        print("Already patched (marker present). Nothing to do.")
        return

    # Detect and honour the file's newline convention
    crlf = "\r\n" in src

    def conv(s):
        return s.replace("\n", "\r\n") if crlf else s

    # Verify every anchor first so a partial patch is impossible
    for anchor, _ in EDITS:
        a = conv(anchor)
        n = src.count(a)
        if n == 0:
            fail(f"anchor not found: {anchor[:60]!r}...")
        if n > 1:
            fail(f"anchor not unique ({n} occurrences): {anchor[:60]!r}...")

    backup = TARGET.with_suffix(f".backup-{time.strftime('%Y%m%d-%H%M%S')}.html")
    with open(backup, "w", encoding="utf-8", newline="") as f:
        f.write(src)

    for anchor, replacement in EDITS:
        src = src.replace(conv(anchor), conv(replacement), 1)

    with open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(src)

    print(f"Patched {TARGET} (4 edits)")
    print(f"Backup written to {backup.name}")
    print("Cold start now shows today's stored picks and never persists")
    print("picks derived from the saved-only track set.")


if __name__ == "__main__":
    main()
