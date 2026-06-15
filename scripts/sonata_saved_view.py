#!/usr/bin/env python3
"""
sonata_saved_view.py

Defines the missing renderSavedView() function.

Background
----------
renderView() dispatches to renderSavedView() (currentView === 'saved') but the
function was never defined. Calling it throws a ReferenceError that aborts
renderView() after it has already cleared drillTarget and flagged the Saved tab
active, but before any content is written. The content area keeps whatever was
last on screen, so saved state appears to bleed onto Home and only a Reshuffle
(a clean home re-render) clears it.

This patch adds a proper renderSavedView() so:
  - Saved music is shown only on the Saved page.
  - Home is left entirely to renderHomeView() and always shows the 12 picks.

The view groups saved tracks by album and renders the standard album grid.
Tapping a card drills into the album (Back returns to the Saved grid).

Convention
----------
Idempotent (marker check), timestamped backup, loud failure on a missing or
non-unique anchor. Anchor strings use \\n. Run from the repo root.
"""

import sys
import time
from pathlib import Path

TARGET = Path("sonata-pwa.html")
MARKER = "// renderSavedView built by sonata_saved_view.py"

# Insert immediately before the Albums view. renderAlbumView is unique in the
# file; anchoring on the ASCII function line avoids matching the box-drawing
# comment dashes above it.
ANCHOR = "\nfunction renderAlbumView() {\n"

NEW_FUNCTION = """
// ── Saved view ────────────────────────────────────────────────────────────────
""" + MARKER + """
function renderSavedView() {
  // Drilling into a saved album reuses the standard track list. Keep this guard
  // first, exactly like renderAlbumView, so Back returns here.
  if (state.drillTarget) { renderTrackList(getVisibleTracks()); return; }

  const content = document.getElementById('content');

  // Group saved tracks by album (album||albumArtist), mirroring the Albums view.
  const map = {};
  for (const t of state.tracks) {
    if (!state.savedIds.has(t.id)) continue;
    const aa  = t.albumArtist || t.artist;
    const key = t.album + '||' + aa;
    if (!map[key]) map[key] = { album: t.album, artist: aa, count: 0, seed: t.artSeed, artUrl: t.artUrl || null };
    map[key].count++;
  }

  const cards = Object.values(map)
    .sort((a, b) => a.album.localeCompare(b.album))
    .map(info => `
    <div class="grid-card" data-album="${esc(info.album)}" data-artist="${esc(info.artist)}">
      <div class="card-art"><canvas class="art-canvas" data-seed="${esc(info.seed)}" data-arturl="${esc(info.artUrl || '')}" data-size="160"></canvas></div>
      <div class="card-label">${esc(info.album)}</div>
      <div class="card-sublabel">
        <span class="clickable-artist" data-artist="${esc(info.artist)}">${esc(info.artist)}</span>
      </div>
    </div>`).join('');

  const count = Object.keys(map).length;

  content.innerHTML = `
    <div class="section-header"><span class="section-title">Saved</span><span class="section-count">${count} album${count !== 1 ? 's' : ''}</span></div>
    <div class="grid-view">${cards || '<div style="padding:24px;color:var(--text3);font-size:13px">No saved music yet. Save an album from its page to keep it offline.</div>'}</div>`;

  initArtCanvases();

  content.querySelectorAll('.grid-card').forEach(card => {
    card.onclick = () => {
      state.drillTarget = { type: 'album', value: card.dataset.album, artist: card.dataset.artist };
      renderView();   // currentView stays 'saved', so Back returns to the Saved grid
    };
  });
}

"""


def fail(msg):
    print("FAILED: " + msg)
    sys.exit(1)


def main():
    if not TARGET.exists():
        fail(f"{TARGET} not found. Run from the repo root.")

    src = TARGET.read_text(encoding="utf-8")

    if MARKER in src:
        print("Already patched (marker present). Nothing to do.")
        return

    n = src.count(ANCHOR)
    if n == 0:
        fail("anchor not found: '\\nfunction renderAlbumView() {\\n'")
    if n > 1:
        fail(f"anchor not unique ({n} occurrences): '\\nfunction renderAlbumView() {{\\n'")

    backup = TARGET.with_suffix(f".backup-{time.strftime('%Y%m%d-%H%M%S')}.html")
    backup.write_text(src, encoding="utf-8")

    patched = src.replace(ANCHOR, "\n" + NEW_FUNCTION + "function renderAlbumView() {\n", 1)
    TARGET.write_text(patched, encoding="utf-8")

    print(f"Patched {TARGET}")
    print(f"Backup written to {backup.name}")
    print("renderSavedView() defined. Tap Saved to verify; Home is untouched.")


if __name__ == "__main__":
    main()
