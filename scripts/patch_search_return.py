#!/usr/bin/env python3
"""
patch_search_return.py

Makes the back button return to the search results when you drilled in from a
search, instead of dumping you on the master Artists or Albums library.

How: extends the existing drillOrigin mechanism with a 'search' origin. Clicking
an artist or album tile in the search view now records drillOrigin = 'search' and
stashes the query in state.searchReturn. The back button on the artist and album
drill-downs detects that origin and restores the search view (query and all) via
a small _restoreSearch() helper, so you can pick a different result without
searching again.

Requires the album-tiles patch (patch_search_albums.py, marker
'sonata-search-albums') to be applied first, since it edits that album tile
handler too.

Touches renderSearchView (tile handlers), renderTrackList (back label + handler)
and renderArtistAlbums (back label + handler). Safe to run repeatedly:
idempotent on the marker 'sonata-search-return'. Creates a timestamped backup.
Fails loudly if any anchor is missing or ambiguous.

Run from the repo root:
    cd C:\\Users\\peter\\repos\\sonata
    python scripts\\patch_search_return.py
"""

import sys
import datetime
from pathlib import Path

TARGET = Path("sonata-pwa.html")
MARKER = "sonata-search-return"


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

    if "sonata-search-albums" not in text:
        die("the album-tiles patch is required first. Run patch_search_albums.py, "
            "then run this.")

    # ---- 1. _restoreSearch helper, injected before renderSearchView ----
    helper = (
        "// " + MARKER + ": return to the search results after drilling into a tile.\n"
        "function _restoreSearch() {\n"
        "  state.drillTarget = null;\n"
        "  state.drillOrigin = null;\n"
        "  state.searchQ = state.searchReturn || '';\n"
        "  state.searchReturn = null;\n"
        "  state.currentView = 'search';\n"
        "  const _s = document.getElementById('search');     if (_s) _s.value = state.searchQ;\n"
        "  const _m = document.getElementById('mob-search');  if (_m) _m.value = state.searchQ;\n"
        "  renderView();\n"
        "}\n"
        "\n"
        "function renderSearchView() {"
    )
    text = apply(text, "function renderSearchView() {", helper,
                 "renderSearchView definition")

    # ---- 2. Artist tile click: record origin + stash query ----
    art_old = (
        "      state.drillTarget = { type: 'artist', value: card.dataset.artist };\n"
        "      state.currentView = 'artists';\n"
        "      state.searchQ = '';"
    )
    art_new = (
        "      state.drillTarget = { type: 'artist', value: card.dataset.artist };\n"
        "      state.currentView = 'artists';\n"
        "      state.drillOrigin = 'search';\n"
        "      state.searchReturn = state.searchQ;\n"
        "      state.searchQ = '';"
    )
    text = apply(text, art_old, art_new, "artist tile handler")

    # ---- 3. Album tile click: record origin + stash query ----
    alb_old = (
        "      state.drillTarget = { type: 'album', value: card.dataset.album, artist: card.dataset.artist };\n"
        "      state.currentView = 'albums';\n"
        "      state.searchQ = '';"
    )
    alb_new = (
        "      state.drillTarget = { type: 'album', value: card.dataset.album, artist: card.dataset.artist };\n"
        "      state.currentView = 'albums';\n"
        "      state.drillOrigin = 'search';\n"
        "      state.searchReturn = state.searchQ;\n"
        "      state.searchQ = '';"
    )
    text = apply(text, alb_old, alb_new, "album tile handler")

    # ---- 4. Album drill-down back label ----
    lbl_old = "  const defaultBackLabel = (state.drillOrigin === 'home' && !backFn) ? 'Home' : 'Back';"
    lbl_new = (
        "  const defaultBackLabel = (state.drillOrigin === 'search' && !backFn) ? 'Search results'\n"
        "                         : (state.drillOrigin === 'home' && !backFn) ? 'Home' : 'Back';"
    )
    text = apply(text, lbl_old, lbl_new, "default back label")

    # ---- 5. Album drill-down back handler (renderTrackList) ----
    h1_old = (
        "      : () => {\n"
        "          // Tweak 8: if we drilled in from home, back returns to home.\n"
        "          if (state.drillOrigin === 'home') {"
    )
    h1_new = (
        "      : () => {\n"
        "          if (state.drillOrigin === 'search') { _restoreSearch(); return; }\n"
        "          // Tweak 8: if we drilled in from home, back returns to home.\n"
        "          if (state.drillOrigin === 'home') {"
    )
    text = apply(text, h1_old, h1_new, "renderTrackList back handler")

    # ---- 6a. Artist drill-down back label (renderArtistAlbums) ----
    artlbl_old = (
        "      <svg width=\"14\" height=\"14\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2.5\" viewBox=\"0 0 24 24\"><polyline points=\"15 18 9 12 15 6\"/></svg>\n"
        "      Artists\n"
        "    </button>"
    )
    artlbl_new = (
        "      <svg width=\"14\" height=\"14\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2.5\" viewBox=\"0 0 24 24\"><polyline points=\"15 18 9 12 15 6\"/></svg>\n"
        "      ${state.drillOrigin === 'search' ? 'Search results' : 'Artists'}\n"
        "    </button>"
    )
    text = apply(text, artlbl_old, artlbl_new, "artist-albums back label")

    # ---- 6b. Artist drill-down back handler (renderArtistAlbums) ----
    h2_old = (
        "  document.getElementById('back-btn').onclick = () => {\n"
        "    state.drillTarget = null;\n"
        "    renderView();\n"
        "  };\n"
        "\n"
        "  content.querySelectorAll('.grid-card').forEach(card => {\n"
        "    card.onclick = () => {\n"
        "      state.drillTarget = {\n"
        "        type:   'artist-album',"
    )
    h2_new = (
        "  document.getElementById('back-btn').onclick = () => {\n"
        "    if (state.drillOrigin === 'search') { _restoreSearch(); return; }\n"
        "    state.drillTarget = null;\n"
        "    renderView();\n"
        "  };\n"
        "\n"
        "  content.querySelectorAll('.grid-card').forEach(card => {\n"
        "    card.onclick = () => {\n"
        "      state.drillTarget = {\n"
        "        type:   'artist-album',"
    )
    text = apply(text, h2_old, h2_new, "artist-albums back handler")

    # ---- backup (exact bytes) + write ----
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = TARGET.with_name(TARGET.name + ".bak-" + stamp)
    backup.write_bytes(TARGET.read_bytes())
    TARGET.write_text(text, encoding="utf-8")  # \n -> CRLF on Windows

    print("Patched %s" % TARGET)
    print("Backup  %s" % backup)


if __name__ == "__main__":
    main()
