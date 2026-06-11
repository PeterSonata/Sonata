#!/usr/bin/env python3
"""
patch_search_albums.py

Reworks the search results into three clear kinds: artist tiles, album tiles,
and a track list.

Before: tracks matched on title OR album name, so searching "pepper" buried the
album among tracks like "A Day In The Life" (matched only because its album is
"Sgt Pepper's..."), and there was no way to land on the album itself.

After:
  - Track list matches the term in the track TITLE only.
  - Album-name matches surface as their own album tiles, grouped per
    album+artist, clickable straight through to the album. Works for any album
    category, since the album drill-down filters by album name.
  - Artist tiles are unchanged.

So "pepper" gives an album tile for "Sgt Pepper's Lonely Hearts Club Band" plus
the Sgt Pepper title tracks, but not "A Day In The Life".

Touches only renderSearchView. Safe to run repeatedly: idempotent on the marker
'sonata-search-albums'. Creates a timestamped backup. Fails loudly if any
anchor is missing or ambiguous.

Run from the repo root:
    cd C:\\Users\\peter\\repos\\sonata
    python scripts\\patch_search_albums.py
"""

import sys
import datetime
from pathlib import Path

TARGET = Path("sonata-pwa.html")
MARKER = "sonata-search-albums"


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

    # ---- 1. Tracks match on title only; build album-name matches ----
    a_old = (
        "  // Matching tracks (title or album, not already covered by artist match)\n"
        "  // Round 1 addendum: cap rendered tracks. allMatchedTracks keeps the\n"
        "  // full count for the section label.\n"
        "  const allMatchedTracks = state.tracks.filter(t =>\n"
        "    t.title.toLowerCase().includes(q) || t.album.toLowerCase().includes(q)\n"
        "  );\n"
        "  const matchedTracks = allMatchedTracks.slice(0, 100);"
    )
    a_new = (
        "  // " + MARKER + ": tracks match on TITLE only now; album-name matches\n"
        "  // surface as their own album tiles instead of polluting the track list.\n"
        "  const allMatchedTracks = state.tracks.filter(t => t.title.toLowerCase().includes(q));\n"
        "  const matchedTracks = allMatchedTracks.slice(0, 100);\n"
        "\n"
        "  // Matching albums (album title contains the term), grouped per album+artist.\n"
        "  // Any category: the album drill-down filters purely by album name.\n"
        "  const albumMap = {};\n"
        "  for (const t of state.tracks) {\n"
        "    if (!t.album || !t.album.toLowerCase().includes(q)) continue;\n"
        "    const aa = t.albumArtist || t.artist;\n"
        "    const key = t.album + '||' + aa;\n"
        "    if (!albumMap[key]) albumMap[key] = { album: t.album, artist: aa, seed: t.artSeed, artUrl: t.artUrl };\n"
        "  }\n"
        "  const allMatchedAlbums = Object.values(albumMap).sort((a,b) => a.album.localeCompare(b.album));\n"
        "  const matchedAlbums = allMatchedAlbums.slice(0, 48);"
    )
    text = apply(text, a_old, a_new, "track-match block")

    # ---- 2. Album tiles section, inserted before the track section ----
    b_old = (
        "  // Track results section\n"
        "  if (matchedTracks.length) {"
    )
    b_new = (
        "  // Album tiles section\n"
        "  if (matchedAlbums.length) {\n"
        "    const acards = matchedAlbums.map(info => `\n"
        "      <div class=\"grid-card search-album-card\" data-album=\"${esc(info.album)}\" data-artist=\"${esc(info.artist)}\">\n"
        "        <div class=\"card-art\"><canvas class=\"art-canvas\" data-seed=\"${esc(info.seed)}\" data-arturl=\"${esc(info.artUrl || '')}\" data-size=\"160\"></canvas></div>\n"
        "        <div class=\"card-label\">${esc(info.album)}</div>\n"
        "        <div class=\"card-sublabel\">${esc(info.artist)}</div>\n"
        "      </div>`).join('');\n"
        "    const _albumTrunc = allMatchedAlbums.length > matchedAlbums.length\n"
        "      ? ` <span style=\"font-weight:400;opacity:0.6\">(showing ${matchedAlbums.length} of ${allMatchedAlbums.length})</span>`\n"
        "      : '';\n"
        "    html += `\n"
        "      <div class=\"search-section-label\">Albums${_albumTrunc}</div>\n"
        "      <div class=\"grid-view\" style=\"border-top:none\">${acards}</div>`;\n"
        "  }\n"
        "\n"
        "  // Track results section\n"
        "  if (matchedTracks.length) {"
    )
    text = apply(text, b_old, b_new, "album tiles section insert")

    # ---- 3. Rename the track section label ----
    c_old = (
        "    html += `<div class=\"search-section-label\" style=\"margin-top:0\">Tracks &amp; Albums "
        "<span style=\"font-weight:400;opacity:0.6\">(${_tracksLabel})</span></div>`;"
    )
    c_new = (
        "    html += `<div class=\"search-section-label\" style=\"margin-top:0\">Tracks "
        "<span style=\"font-weight:400;opacity:0.6\">(${_tracksLabel})</span></div>`;"
    )
    text = apply(text, c_old, c_new, "track section label")

    # ---- 4. Empty-state condition includes albums ----
    d_old = "  if (!matchedArtists.length && !matchedTracks.length) {"
    d_new = "  if (!matchedArtists.length && !matchedAlbums.length && !matchedTracks.length) {"
    text = apply(text, d_old, d_new, "empty-state condition")

    # ---- 5. Album tile click handler ----
    e_old = (
        "  content.querySelectorAll('.search-artist-card').forEach(card => {\n"
        "    card.onclick = () => {\n"
        "      state.drillTarget = { type: 'artist', value: card.dataset.artist };\n"
        "      state.currentView = 'artists';\n"
        "      state.searchQ = '';\n"
        "      document.getElementById('search').value = '';\n"
        "      document.getElementById('mob-search').value = '';\n"
        "      renderView();\n"
        "    };\n"
        "  });"
    )
    e_new = e_old + (
        "\n\n"
        "  content.querySelectorAll('.search-album-card').forEach(card => {\n"
        "    card.onclick = () => {\n"
        "      state.drillTarget = { type: 'album', value: card.dataset.album, artist: card.dataset.artist };\n"
        "      state.currentView = 'albums';\n"
        "      state.searchQ = '';\n"
        "      document.getElementById('search').value = '';\n"
        "      document.getElementById('mob-search').value = '';\n"
        "      renderView();\n"
        "    };\n"
        "  });"
    )
    text = apply(text, e_old, e_new, "album tile click handler")

    # ---- backup (exact bytes) + write ----
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = TARGET.with_name(TARGET.name + ".bak-" + stamp)
    backup.write_bytes(TARGET.read_bytes())
    TARGET.write_text(text, encoding="utf-8")  # \n -> CRLF on Windows

    print("Patched %s" % TARGET)
    print("Backup  %s" % backup)


if __name__ == "__main__":
    main()
