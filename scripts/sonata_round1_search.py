#!/usr/bin/env python3
"""
Sonata PWA - April 2026 tweaks, Round 1 addendum: search performance
====================================================================

Fixes the laggy search bar. Symptom: typing into the search input lags
several seconds before each keystroke appears, especially on iPhone.

Cause: every keystroke walks all ~42,000 tracks twice, builds an HTML
string for every match (no cap), and re-renders the DOM. The main
thread is so busy the browser cannot repaint the input itself.

Three changes:

  A. Debounce the input (150 ms). One render per typing burst, not one
     per keystroke. Single shared handler used by desktop and mobile.
  B. Skip the search entirely until the query is at least 2 characters.
  C. Cap rendered results: 30 artist tiles, 100 tracks. The section
     labels show "showing X of Y" when truncated.

USAGE
-----
Run AFTER sonata_round1.py, in the same folder as sonata-pwa.html:

    python sonata_round1_search.py

Default behaviour:
  - Reads:  sonata-pwa.html
  - Writes: sonata-pwa.html (in place)
  - Backs up the original to: sonata-pwa.backup-round1-search.html

Pass a different filename if your file is named something else:

    python sonata_round1_search.py my-sonata.html

The script anchors on the POST-Round-1 source (where 'all' has already
been rewritten to 'home' in the search handlers). If you run this on a
file that has not had Round 1 applied, it will bail loudly without
modifying anything.
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
            f"  Did you run sonata_round1.py first?\n"
            f"  Expected substring (first 160 chars):\n  {old[:160]!r}"
        )
    if count > 1:
        raise SystemExit(
            f"FAIL [{label}]: anchor found {count} times, must be unique.\n"
            f"  Substring (first 160 chars):\n  {old[:160]!r}"
        )
    return html.replace(old, new, 1)


# ---------------------------------------------------------------------------
# A. Debounce + min-length on the input handlers
# ---------------------------------------------------------------------------

def patch_debounce(html: str) -> str:
    # Replace the desktop search handler with a shared, debounced one.
    html = must_replace(
        html,
        "// Search (desktop)\n"
        "document.getElementById('search').oninput = (e) => {\n"
        "  state.searchQ = e.target.value.toLowerCase().trim();\n"
        "  state.currentView = state.searchQ ? 'search' : 'home';\n"
        "  state.drillTarget = null;\n"
        "  renderView();\n"
        "};\n",
        "// Search (debounced, shared by desktop and mobile inputs)\n"
        "// Round 1 addendum: avoid running the full search on every keystroke,\n"
        "// which was blocking the main thread for seconds at a time on iPhone.\n"
        "let _searchTimer = null;\n"
        "function _onSearchInput(value) {\n"
        "  clearTimeout(_searchTimer);\n"
        "  _searchTimer = setTimeout(() => {\n"
        "    const q = value.toLowerCase().trim();\n"
        "    // Single-character queries match too broadly to be useful and slow\n"
        "    // the app right down. Wait until we have at least two characters.\n"
        "    state.searchQ = q.length >= 2 ? q : '';\n"
        "    state.currentView = state.searchQ ? 'search' : 'home';\n"
        "    state.drillTarget = null;\n"
        "    renderView();\n"
        "  }, 150);\n"
        "}\n"
        "document.getElementById('search').oninput = (e) => _onSearchInput(e.target.value);\n",
        'search.desktop-debounce',
    )

    # Replace the mobile oninput with the same shared handler.
    html = must_replace(
        html,
        "document.getElementById('mob-search').oninput = (e) => {\n"
        "  state.searchQ = e.target.value.toLowerCase().trim();\n"
        "  state.currentView = state.searchQ ? 'search' : 'home';\n"
        "  state.drillTarget = null;\n"
        "  renderView();\n"
        "};\n",
        "document.getElementById('mob-search').oninput = (e) => _onSearchInput(e.target.value);\n",
        'search.mobile-debounce',
    )

    return html


# ---------------------------------------------------------------------------
# B/C. Cap rendered results in renderSearchView
# ---------------------------------------------------------------------------

def patch_result_caps(html: str) -> str:
    # Cap matched artists: keep a separate "all" list for the count display.
    html = must_replace(
        html,
        "  const matchedArtists = Object.entries(artistMap)\n"
        "    .filter(([name]) => name.toLowerCase().includes(q))\n"
        "    .sort((a,b) => a[0].localeCompare(b[0]));\n",
        "  // Round 1 addendum: cap rendered artist tiles to keep the search\n"
        "  // view snappy. allMatchedArtists keeps the full count for display.\n"
        "  const allMatchedArtists = Object.entries(artistMap)\n"
        "    .filter(([name]) => name.toLowerCase().includes(q))\n"
        "    .sort((a,b) => a[0].localeCompare(b[0]));\n"
        "  const matchedArtists = allMatchedArtists.slice(0, 30);\n",
        'search.cap-artists',
    )

    # Cap matched tracks the same way.
    html = must_replace(
        html,
        "  // Matching tracks (title or album, not already covered by artist match)\n"
        "  const matchedTracks = state.tracks.filter(t =>\n"
        "    t.title.toLowerCase().includes(q) || t.album.toLowerCase().includes(q)\n"
        "  );\n",
        "  // Matching tracks (title or album, not already covered by artist match)\n"
        "  // Round 1 addendum: cap rendered tracks. allMatchedTracks keeps the\n"
        "  // full count for the section label.\n"
        "  const allMatchedTracks = state.tracks.filter(t =>\n"
        "    t.title.toLowerCase().includes(q) || t.album.toLowerCase().includes(q)\n"
        "  );\n"
        "  const matchedTracks = allMatchedTracks.slice(0, 100);\n",
        'search.cap-tracks',
    )

    # Artists section label: show "(showing 30 of 142)" when truncated.
    html = must_replace(
        html,
        "    html += `\n"
        "      <div class=\"search-section-label\">Artists</div>\n"
        "      <div class=\"grid-view\" style=\"border-top:none\">${cards}</div>`;\n",
        "    const _artistTrunc = allMatchedArtists.length > matchedArtists.length\n"
        "      ? ` <span style=\"font-weight:400;opacity:0.6\">(showing ${matchedArtists.length} of ${allMatchedArtists.length})</span>`\n"
        "      : '';\n"
        "    html += `\n"
        "      <div class=\"search-section-label\">Artists${_artistTrunc}</div>\n"
        "      <div class=\"grid-view\" style=\"border-top:none\">${cards}</div>`;\n",
        'search.artists-section-label',
    )

    # Tracks section label: show "100 of 4,872" when truncated.
    html = must_replace(
        html,
        "    html += `<div class=\"search-section-label\" style=\"margin-top:0\">Tracks &amp; Albums <span style=\"font-weight:400;opacity:0.6\">(${matchedTracks.length})</span></div>`;\n",
        "    const _tracksLabel = allMatchedTracks.length > matchedTracks.length\n"
        "      ? `${matchedTracks.length} of ${allMatchedTracks.length.toLocaleString()}`\n"
        "      : `${matchedTracks.length}`;\n"
        "    html += `<div class=\"search-section-label\" style=\"margin-top:0\">Tracks &amp; Albums <span style=\"font-weight:400;opacity:0.6\">(${_tracksLabel})</span></div>`;\n",
        'search.tracks-section-label',
    )

    return html


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def main() -> None:
    src_path = Path(sys.argv[1] if len(sys.argv) > 1 else 'sonata-pwa.html')
    if not src_path.exists():
        raise SystemExit(f"Source file not found: {src_path}")

    backup_path = src_path.with_name(src_path.stem + '.backup-round1-search.html')
    shutil.copy(src_path, backup_path)
    print(f"[backup] {backup_path}")

    html = src_path.read_text(encoding='utf-8')
    print(f"[input ] {len(html):,} bytes")

    html = patch_debounce(html)
    html = patch_result_caps(html)

    src_path.write_text(html, encoding='utf-8')
    print(f"[output] {len(html):,} bytes -> {src_path}")
    print()
    print("Round 1 search performance patch complete.")
    print("Reload Sonata (Ctrl+F5) to see the change.")
    print("Verify: typing in the search box no longer lags, single characters")
    print("are ignored, and very common queries show 'showing X of Y' counts.")


if __name__ == '__main__':
    main()
