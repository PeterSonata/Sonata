#!/usr/bin/env python3
"""
Sonata PWA - Round 1 follow-up: pass artist through on album drill-downs
========================================================================

Round 1 Tweak 3 made artist names tappable wherever they appear on
album pages. But on albums drilled into from the Home screen or the
Albums grid, no artist name appeared at all. The drill handlers were
setting drillTarget = { type: 'album', value: album }, with no artist
field, so the album hero had nothing to render.

This patcher adds:

  A. data-artist attribute on the home album card
  B. card.dataset.artist passed to drillTarget in the home click handler
  C. data-artist attribute on the albums grid card
  D. card.dataset.artist passed to drillTarget in the albums grid click

After this, drilling into an album from anywhere shows the artist name
under the album title, and that name is tappable (per Tweak 3).

USAGE
-----
Run AFTER sonata_round1.py, in the same folder as sonata-pwa.html:

    python sonata_round1_artist_drill.py

Default behaviour:
  - Reads:  sonata-pwa.html
  - Writes: sonata-pwa.html (in place)
  - Backs up the original to: sonata-pwa.backup-round1-artist-drill.html

Pass a different filename if needed:

    python sonata_round1_artist_drill.py my-sonata.html
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
            f"  Expected substring (first 200 chars):\n  {old[:200]!r}"
        )
    if count > 1:
        raise SystemExit(
            f"FAIL [{label}]: anchor found {count} times, must be unique.\n"
            f"  Substring (first 200 chars):\n  {old[:200]!r}"
        )
    return html.replace(old, new, 1)


# ---------------------------------------------------------------------------
# A. Home album card: add data-artist attribute
# ---------------------------------------------------------------------------

def patch_home_card_attribute(html: str) -> str:
    return must_replace(
        html,
        '<div class="grid-card home-album-card${inSelect ? \' qf-selecting\' : \'\'}${isSel ? \' qf-selected\' : \'\'}" data-album="${esc(info.album)}" data-type="${info._type || \'album\'}">',
        '<div class="grid-card home-album-card${inSelect ? \' qf-selecting\' : \'\'}${isSel ? \' qf-selected\' : \'\'}" data-album="${esc(info.album)}" data-type="${info._type || \'album\'}" data-artist="${esc(info.artist)}">',
        'home-card.data-artist',
    )


# ---------------------------------------------------------------------------
# B. Home click handler: pass artist into drillTarget
# ---------------------------------------------------------------------------

def patch_home_click_handler(html: str) -> str:
    return must_replace(
        html,
        "      state.drillOrigin = 'home';\n"
        "      state.currentView = type === 'compilation' ? 'compilations' : (type === 'djmix' ? 'djmixes' : 'albums');\n"
        "      state.drillTarget = { type: type === 'compilation' ? 'compilation' : (type === 'djmix' ? 'djmix' : 'album'), value: album };\n",
        "      state.drillOrigin = 'home';\n"
        "      state.currentView = type === 'compilation' ? 'compilations' : (type === 'djmix' ? 'djmixes' : 'albums');\n"
        "      // Round 1 follow-up: pass artist through so the album page can show and link it.\n"
        "      const drillType = type === 'compilation' ? 'compilation' : (type === 'djmix' ? 'djmix' : 'album');\n"
        "      state.drillTarget = drillType === 'album'\n"
        "        ? { type: 'album', value: album, artist: card.dataset.artist }\n"
        "        : { type: drillType, value: album };\n",
        'home-click.drillTarget',
    )


# ---------------------------------------------------------------------------
# C. Albums grid card: add data-artist attribute
# ---------------------------------------------------------------------------

def patch_grid_card_attribute(html: str) -> str:
    return must_replace(
        html,
        '<div class="grid-card" data-album="${esc(info.album)}">\n'
        '      <div class="card-art"><canvas class="art-canvas" data-seed="${esc(info.seed)}" data-arturl="${esc(info.artUrl || \'\')}" data-size="160"></canvas></div>\n'
        '      <div class="card-label">${esc(info.album)}</div>\n'
        '      <div class="card-sublabel" style="display:flex;align-items:center;justify-content:space-between">\n'
        '        <span class="clickable-artist" data-artist="${esc(info.artist)}">${esc(info.artist)}</span>',
        '<div class="grid-card" data-album="${esc(info.album)}" data-artist="${esc(info.artist)}">\n'
        '      <div class="card-art"><canvas class="art-canvas" data-seed="${esc(info.seed)}" data-arturl="${esc(info.artUrl || \'\')}" data-size="160"></canvas></div>\n'
        '      <div class="card-label">${esc(info.album)}</div>\n'
        '      <div class="card-sublabel" style="display:flex;align-items:center;justify-content:space-between">\n'
        '        <span class="clickable-artist" data-artist="${esc(info.artist)}">${esc(info.artist)}</span>',
        'grid-card.data-artist',
    )


# ---------------------------------------------------------------------------
# D. Albums grid click handler: pass artist into drillTarget
# ---------------------------------------------------------------------------

def patch_grid_click_handler(html: str) -> str:
    return must_replace(
        html,
        "    card.onclick = () => { state.drillTarget = { type: 'album', value: card.dataset.album }; renderView(); };\n",
        "    card.onclick = () => { state.drillTarget = { type: 'album', value: card.dataset.album, artist: card.dataset.artist }; renderView(); };\n",
        'grid-click.drillTarget',
    )


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def main() -> None:
    src_path = Path(sys.argv[1] if len(sys.argv) > 1 else 'sonata-pwa.html')
    if not src_path.exists():
        raise SystemExit(f"Source file not found: {src_path}")

    backup_path = src_path.with_name(src_path.stem + '.backup-round1-artist-drill.html')
    shutil.copy(src_path, backup_path)
    print(f"[backup] {backup_path}")

    html = src_path.read_text(encoding='utf-8')
    print(f"[input ] {len(html):,} bytes")

    html = patch_home_card_attribute(html)
    html = patch_home_click_handler(html)
    html = patch_grid_card_attribute(html)
    html = patch_grid_click_handler(html)

    src_path.write_text(html, encoding='utf-8')
    print(f"[output] {len(html):,} bytes -> {src_path}")
    print()
    print("Round 1 follow-up complete. Reload Sonata (Ctrl+F5) to see the change.")
    print("Verify: drilling into an album from Home or Albums grid now shows")
    print("the artist name beneath the title, and that name is tappable.")


if __name__ == '__main__':
    main()
