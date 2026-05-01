#!/usr/bin/env python3
"""
Sonata PWA - album hero save button + DJ mix drilldown fix
============================================================

Two related quality-of-life fixes:

  A. Add a Save All button to the album hero on drilldown pages. The
     existing Save All only renders in the section header, which is
     suppressed whenever the album hero is shown. So albums, artist-
     albums, compilations, and DJ mixes had no way to save the whole
     collection from the track listing page.

  B. Make renderDJMixesView short-circuit to renderTrackList when
     drillTarget.type === 'djmix'. Without this, clicking a DJ-mix-
     classified album from the home screen falls through to the Level 1
     grid of DJs instead of showing the track listing. Compilations
     view already does this; DJ mixes view should match.

The Save button uses the existing id="save-all-btn" so the existing
wiring (document.getElementById('save-all-btn').onclick = ...) picks
it up automatically. The two render paths (album hero vs section
header) are mutually exclusive, so there's never a clash.

USAGE
-----
Run in the same folder as sonata-pwa.html:

    python sonata_album_hero_save.py

Default behaviour:
  - Reads:  sonata-pwa.html
  - Writes: sonata-pwa.html (in place)
  - Backs up to: sonata-pwa.backup-album-hero-save.html
"""
from __future__ import annotations
import sys
import shutil
from pathlib import Path


def must_replace(html: str, old: str, new: str, label: str) -> str:
    count = html.count(old)
    if count == 0:
        raise SystemExit(
            f"FAIL [{label}]: anchor not found.\n"
            f"  Substring (first 200 chars):\n  {old[:200]!r}"
        )
    if count > 1:
        raise SystemExit(
            f"FAIL [{label}]: anchor found {count} times.\n"
            f"  Substring (first 200 chars):\n  {old[:200]!r}"
        )
    return html.replace(old, new, 1)


# ---------------------------------------------------------------------------
# A. Album hero: wrap Play in a flex row with a new Save All button
# ---------------------------------------------------------------------------

def patch_album_hero_save(html: str) -> str:
    return must_replace(
        html,
        '        <div class="album-hero-meta">${year ? year + \' · \' : \'\'}${tracks.length} track${tracks.length !== 1 ? \'s\' : \'\'}</div>\n'
        '        <button class="play-all-btn" id="play-all-btn">\n'
        '          <svg width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>\n'
        '          Play\n'
        '        </button>\n',
        '        <div class="album-hero-meta">${year ? year + \' · \' : \'\'}${tracks.length} track${tracks.length !== 1 ? \'s\' : \'\'}</div>\n'
        '        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">\n'
        '          <button class="play-all-btn" id="play-all-btn">\n'
        '            <svg width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>\n'
        '            Play\n'
        '          </button>\n'
        '          ${mob ? `<button class="save-collection-btn${allSaved ? \' all-saved\' : \'\'}" id="save-all-btn">\n'
        '            <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>\n'
        '            ${allSaved ? \'All Saved\' : \'Save All\'}\n'
        '          </button>` : \'\'}\n'
        '        </div>\n',
        'album-hero.save-button',
    )


# ---------------------------------------------------------------------------
# B. renderDJMixesView: short-circuit on djmix drilldown
# ---------------------------------------------------------------------------

def patch_djmix_drill(html: str) -> str:
    return must_replace(
        html,
        'function renderDJMixesView() {\n'
        '  const content = document.getElementById(\'content\');\n'
        '  ensureIndexes();\n',
        'function renderDJMixesView() {\n'
        '  // If drilling into a specific DJ mix, render the track listing\n'
        '  // (matches how renderCompilationsView and renderAlbumView behave).\n'
        '  if (state.drillTarget && state.drillTarget.type === \'djmix\') {\n'
        '    renderTrackList(getVisibleTracks());\n'
        '    return;\n'
        '  }\n'
        '  const content = document.getElementById(\'content\');\n'
        '  ensureIndexes();\n',
        'djmix.drill-shortcut',
    )


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def main() -> None:
    src_path = Path(sys.argv[1] if len(sys.argv) > 1 else 'sonata-pwa.html')
    if not src_path.exists():
        raise SystemExit(f"Source file not found: {src_path}")

    backup_path = src_path.with_name(src_path.stem + '.backup-album-hero-save.html')
    shutil.copy(src_path, backup_path)
    print(f"[backup] {backup_path}")

    html = src_path.read_text(encoding='utf-8')
    print(f"[input ] {len(html):,} bytes")

    html = patch_album_hero_save(html)
    html = patch_djmix_drill(html)

    src_path.write_text(html, encoding='utf-8')
    print(f"[output] {len(html):,} bytes -> {src_path}")
    print()
    print("Patcher complete. Reload Sonata to see the changes.")
    print()
    print("Verify on iPhone PWA:")
    print("  1. Drill into any album. A 'Save All' button now sits next to")
    print("     'Play' in the album hero. Tap to save all tracks to device.")
    print("  2. From home, tap a DJ-mix-classified album (Pebbles Vol 11).")
    print("     Should now show the track listing, not the grid of DJs.")


if __name__ == '__main__':
    main()
