#!/usr/bin/env python3
"""
patch_artists_shuffle.py  (supersedes the earlier version of the same name)

Reworks the level-1 Artists grid to surface album artists you own but overlook:

  1. Filter: feature an artist only if they have at least ALBUM_MIN_TRACKS (5) on
     some single album title. This is a robust proxy for "owns an album by them":
     it falls back to the track artist when the album-artist tag is missing, and
     it ignores the compilation/DJ-mix classification, so a real album with guest
     credits still counts while a mixtape guest (a track or two on any one album)
     drops out. ALBUM_MIN_TRACKS is the one knob to tune.
  2. Order: shuffle by default. A header button flips to A-Z, and flipping back
     re-rolls a fresh shuffle, so it doubles as a deliberate reshuffle. The
     shuffle is cached so drilling into an artist and back keeps the same order.

Touches only the level-1 grid in renderArtists. Drill-down and canvas art are
unchanged.

NOTE: this replaces the earlier artists patcher (track-count threshold). If you
already ran that one, restore its backup or `git checkout sonata-pwa.html`
first; this patcher anchors on the original grid and will ABORT loudly rather
than touch an already-modified block.

Safe to run repeatedly: idempotent on the marker 'sonata-artist-album-floor'.
Creates a timestamped backup. Fails loudly if the anchor is missing or
ambiguous.

Run from the repo root:
    cd C:\\Users\\peter\\repos\\sonata
    python scripts\\patch_artists_shuffle.py
"""

import sys
import datetime
from pathlib import Path

TARGET = Path("sonata-pwa.html")
MARKER = "sonata-artist-album-floor"


def die(msg):
    print("ABORT: " + msg)
    sys.exit(1)


OLD = """  const filtered = Object.entries(map).filter(([,v]) => v.count > 1);

  const cards = filtered.sort((a,b) => a[0].localeCompare(b[0])).map(([name, info]) => {
    return `
    <div class="grid-card" data-artist="${esc(name)}">
      <div class="card-art">
        <canvas class="art-canvas" data-seed="${esc(info.seed)}" data-size="160"></canvas>
      </div>
      <div class="card-label">${esc(name)}</div>
      <div class="card-sublabel">${info.albumCount} album${info.albumCount !== 1 ? 's' : ''}</div>
    </div>`;
  }).join('');

  content.innerHTML = `
    <div class="section-header"><span class="section-title">Artists</span><span class="section-count">${filtered.length} artists</span></div>
    <div class="grid-view">${cards || '<div style="padding:24px;color:var(--text3);font-size:13px">No artists found</div>'}</div>`;

  initArtCanvases();

  content.querySelectorAll('.grid-card').forEach(card => {
    card.onclick = () => {
      state.drillTarget = { type: 'artist', value: card.dataset.artist };
      renderView();
    };
  });"""


NEW = """  // sonata-artist-album-floor: feature only artists you own an album by, and
  // shuffle the grid by default with a header button to flip to A-Z and back to a
  // fresh shuffle. "Owns an album" is measured as the most tracks the artist has
  // on any single album title. This tolerates a missing album-artist tag (it
  // falls back to the track artist) and ignores compilation/DJ-mix labelling, so
  // a real album with guest credits still counts while a mixtape guest, who only
  // ever has a track or two on any one album, drops out. ALBUM_MIN_TRACKS is the
  // floor for "an album's worth" and is the one knob to tune.
  const ALBUM_MIN_TRACKS = 5;

  // Most tracks each artist has on any single album title.
  const _perAlbum = {};
  for (const t of state.tracks) {
    if (t.saved) continue;
    const aa = t.albumArtist || t.artist;
    if (!aa || isVAName(aa) || aa === 'Unknown Artist') continue;
    if (!_perAlbum[aa]) _perAlbum[aa] = {};
    _perAlbum[aa][t.album] = (_perAlbum[aa][t.album] || 0) + 1;
  }
  const _maxOnOneAlbum = name => {
    const a = _perAlbum[name];
    return a ? Math.max(...Object.values(a)) : 0;
  };

  const filtered = Object.entries(map).filter(([name]) => _maxOnOneAlbum(name) >= ALBUM_MIN_TRACKS);

  if (!state.artistSort) state.artistSort = 'shuffle';
  const names = filtered.map(([name]) => name);
  let order;
  if (state.artistSort === 'alpha') {
    order = names.slice().sort((a, b) => a.localeCompare(b));
  } else {
    // Reuse a cached shuffle so drilling into an artist and back keeps the same
    // order; re-roll only when the set changes or the user asks for it.
    const cached = state._artistShuffle;
    const sameSet = cached && cached.length === names.length && cached.every(n => names.includes(n));
    if (sameSet) {
      order = cached;
    } else {
      order = names.slice();
      for (let i = order.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [order[i], order[j]] = [order[j], order[i]];
      }
      state._artistShuffle = order;
    }
  }

  const byName = new Map(filtered);
  const cards = order.map(name => {
    const info = byName.get(name);
    return `
    <div class="grid-card" data-artist="${esc(name)}">
      <div class="card-art">
        <canvas class="art-canvas" data-seed="${esc(info.seed)}" data-size="160"></canvas>
      </div>
      <div class="card-label">${esc(name)}</div>
      <div class="card-sublabel">${info.albumCount} album${info.albumCount !== 1 ? 's' : ''}</div>
    </div>`;
  }).join('');

  const sortLabel = state.artistSort === 'alpha' ? 'Shuffle' : 'A \u2192 Z';
  content.innerHTML = `
    <div class="section-header" style="justify-content:space-between;align-items:center">
      <span class="section-title">Artists</span>
      <span style="display:inline-flex;align-items:center;gap:14px">
        <span class="section-count">${order.length} artists</span>
        <button class="home-reshuffle" id="artist-sort-btn">${sortLabel}</button>
      </span>
    </div>
    <div class="grid-view">${cards || '<div style="padding:24px;color:var(--text3);font-size:13px">No artists found</div>'}</div>`;

  initArtCanvases();

  const _artistSortBtn = document.getElementById('artist-sort-btn');
  if (_artistSortBtn) _artistSortBtn.onclick = () => {
    if (state.artistSort === 'alpha') {
      state.artistSort = 'shuffle';
      state._artistShuffle = null;   // deliberate flip back re-rolls a fresh shuffle
    } else {
      state.artistSort = 'alpha';
    }
    renderView();
  };

  content.querySelectorAll('.grid-card').forEach(card => {
    card.onclick = () => {
      state.drillTarget = { type: 'artist', value: card.dataset.artist };
      renderView();
    };
  });"""


def main():
    if not TARGET.exists():
        die("%s not found. Run from the repo root." % TARGET)

    text = TARGET.read_text(encoding="utf-8")  # CRLF -> LF in memory on Windows

    if MARKER in text:
        print("Already patched (marker present). Nothing to do.")
        return

    if "sonata-artist-sort" in text:
        die("the earlier track-count artists patch is applied. Restore its backup "
            "or `git checkout sonata-pwa.html`, then run this.")

    n = text.count(OLD)
    if n == 0:
        die("anchor not found: original artists level-1 grid block.")
    if n > 1:
        die("anchor matched %d times (expected exactly 1)" % n)

    text = text.replace(OLD, NEW)

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = TARGET.with_name(TARGET.name + ".bak-" + stamp)
    backup.write_bytes(TARGET.read_bytes())
    TARGET.write_text(text, encoding="utf-8")  # \n -> CRLF on Windows

    print("Patched %s" % TARGET)
    print("Backup  %s" % backup)


if __name__ == "__main__":
    main()
