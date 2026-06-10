#!/usr/bin/env python3
"""
sonata_album_actions_genre.py

Three client features in one pass:

  1. Add to Playlist on the album page. A button in the album hero adds every
     track in the album to a chosen playlist (or a new one) in a single call.
  2. Stronger shuffle/repeat active states. Active shuffle is a solid red block,
     active repeat a solid blue block, white icon, replacing the faint
     icon-only tint.
  3. Genre views by album rather than track. The genre grid counts albums, and
     tapping a genre shows an album grid; tapping an album drills into it, with
     back returning to the genre.

Idempotent, timestamped backup, fails loudly on any missing or non-unique
anchor, matches the file's newline convention. Run from the repo root:
  python scripts\\sonata_album_actions_genre.py
"""

import sys
import time
from pathlib import Path

TARGET = Path("sonata-pwa.html")

# ── 1. CSS: shuffle/repeat pill + album add button ─────────────────────────────
CSS_OLD = ".ctrl-btn.active { color: var(--accent); }"
CSS_NEW = """.ctrl-btn.active { color: var(--accent); }
/* Stronger shuffle/repeat active state: solid colour block, white icon. */
#shuffle-btn.active, #fp-shuffle-btn.active { color: #fff; background: var(--accent); }
#shuffle-btn.active:hover, #fp-shuffle-btn.active:hover { color: #fff; background: var(--accent-dim); }
#repeat-btn.active, #fp-repeat-all-btn.active, #fp-repeat-one-btn.active { color: #fff; background: var(--blue); }
#repeat-btn.active:hover, #fp-repeat-all-btn.active:hover, #fp-repeat-one-btn.active:hover { color: #fff; background: #0d2070; }
#fp-shuffle-btn.active .fp-ctrl-label { color: #fff; }
#fp-repeat-all-btn.active .fp-ctrl-label, #fp-repeat-one-btn.active .fp-ctrl-label { color: #fff; }
/* Album-level Add to Playlist button (outlined, sits beside Play and Save All). */
.add-album-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 14px;
  background: var(--bg);
  border: var(--bw) solid var(--border);
  color: var(--text);
  cursor: pointer;
  font-family: 'IBM Plex Sans', sans-serif;
  font-size: 10px; font-weight: 700;
  letter-spacing: 0.1em; text-transform: uppercase;
  transition: background 0.1s, color 0.1s;
  white-space: nowrap;
  -webkit-tap-highlight-color: transparent;
  flex-shrink: 0;
}
.add-album-btn:hover { background: var(--accent); color: #fff; }
.add-album-btn:active { background: var(--accent2); color: var(--text); }"""

# ── 2. pendingAddTrackIds global ───────────────────────────────────────────────
PENDING_OLD = "let pendingAddTrackId = null;"
PENDING_NEW = "let pendingAddTrackId = null;\nlet pendingAddTrackIds = null;"

# ── 3. addTracksToJellyfinPlaylist helper ──────────────────────────────────────
ADDTRACK_OLD = """async function addTrackToJellyfinPlaylist(playlist, trackId) {
  if (!jellyfin.connected || !playlist.id) return;
  try {
    await jfPost(`/Playlists/${playlist.id}/Items?Ids=${trackId}&UserId=${jellyfin.userId}`, {});
    // Refresh entry IDs for this playlist
    const items = await jfGet(`/Playlists/${playlist.id}/Items?UserId=${jellyfin.userId}`);
    playlist._entryIds = playlist._entryIds || {};
    for (const i of (items.Items || [])) {
      playlist._entryIds[i.Id] = i.PlaylistItemId;
    }
  } catch(e) {
    console.error('Add to playlist error:', e);
  }
}"""
ADDTRACK_NEW = ADDTRACK_OLD + """

async function addTracksToJellyfinPlaylist(playlist, trackIds) {
  if (!jellyfin.connected || !playlist.id || !trackIds.length) return;
  try {
    const ids = trackIds.join(',');
    await jfPost(`/Playlists/${playlist.id}/Items?Ids=${ids}&UserId=${jellyfin.userId}`, {});
    const items = await jfGet(`/Playlists/${playlist.id}/Items?UserId=${jellyfin.userId}`);
    playlist._entryIds = playlist._entryIds || {};
    for (const i of (items.Items || [])) {
      playlist._entryIds[i.Id] = i.PlaylistItemId;
    }
  } catch(e) {
    console.error('Add tracks to playlist error:', e);
  }
}"""

# ── 4. Modal: new-with-tracks branch ───────────────────────────────────────────
MODAL_OLD = """  if (modalMode === 'new-with-track' && pendingAddTrackId) {
    pl.trackIds.push(pendingAddTrackId);
    await addTrackToJellyfinPlaylist(pl, pendingAddTrackId);
  }"""
MODAL_NEW = """  if (modalMode === 'new-with-track' && pendingAddTrackId) {
    pl.trackIds.push(pendingAddTrackId);
    await addTrackToJellyfinPlaylist(pl, pendingAddTrackId);
  } else if (modalMode === 'new-with-tracks' && pendingAddTrackIds && pendingAddTrackIds.length) {
    pl.trackIds.push(...pendingAddTrackIds);
    await addTracksToJellyfinPlaylist(pl, pendingAddTrackIds);
  }"""

# ── 5. showCtxMenu: add-album-to-playlist branch ───────────────────────────────
CTX_OLD = """    const nb = document.getElementById('ctx-new-pl');
    if (nb) nb.onclick = () => { hideCtxMenu(); showModal('new-with-track'); };
  }
}"""
CTX_NEW = """    const nb = document.getElementById('ctx-new-pl');
    if (nb) nb.onclick = () => { hideCtxMenu(); showModal('new-with-track'); };
  }

  if (type === 'add-album-to-playlist') {
    const ids = pendingAddTrackIds || [];
    const items = state.playlists.map(pl => `
      <div class="ctx-item" data-pl-id="${pl.id}">+ ${esc(pl.name)}</div>`).join('');
    ctxMenu.innerHTML = `
      <div class="ctx-label">Add album to playlist</div>
      ${items || '<div class="ctx-item" style="opacity:0.5;cursor:default">No playlists</div>'}
      <div class="ctx-divider"></div>
      <div class="ctx-item" id="ctx-new-pl">+ New playlist…</div>`;
    ctxMenu.querySelectorAll('[data-pl-id]').forEach(el => {
      el.onclick = async () => {
        const pl = state.playlists.find(p => p.id === el.dataset.plId);
        if (pl && ids.length) {
          const toAdd = ids.filter(id => !pl.trackIds.includes(id));
          if (toAdd.length) {
            pl.trackIds.push(...toAdd);
            savePlaylists();
            await addTracksToJellyfinPlaylist(pl, toAdd);
          }
          showToast(`Added ${toAdd.length} track${toAdd.length !== 1 ? 's' : ''} to "${pl.name}"`);
        }
        hideCtxMenu(); renderPlaylists();
      };
    });
    const nb = document.getElementById('ctx-new-pl');
    if (nb) nb.onclick = () => { hideCtxMenu(); showModal('new-with-tracks'); };
  }
}"""

# ── 6. renderGenreView -> by album, plus renderGenreAlbums ──────────────────────
GENRE_OLD = """function renderGenreView() {
  if (state.drillTarget) { renderTrackList(getVisibleTracks()); return; }
  const content = document.getElementById('content');
  const map = {};
  for (const t of state.tracks) { if (!map[t.genre]) map[t.genre] = 0; map[t.genre]++; }
  const colors = ['#d4181b','#1932a0','#f5c518','#d4181b','#f5f3ee','#1932a0','#d4181b','#f5c518','#1932a0','#d4181b'];
  const textColors = ['#fff','#fff','#0d0d0d','#fff','#0d0d0d','#fff','#fff','#0d0d0d','#fff','#fff'];
  const cards = Object.entries(map).sort((a,b) => b[1]-a[1]).map(([name, count], i) => {
    const c = colors[i % colors.length];
    const tc = textColors[i % textColors.length];
    return `
    <div class="genre-card" data-genre="${esc(name)}" style="background:${c}">
      <div class="genre-name" style="color:${tc}">${esc(name)}</div>
      <div class="genre-count" style="color:${tc};opacity:0.7">${count} track${count !== 1 ? 's' : ''}</div>
    </div>`;
  }).join('');
  content.innerHTML = `
    <div class="section-header"><span class="section-title">Genres</span><span class="section-count">${Object.keys(map).length} genres</span></div>
    <div class="genre-grid">${cards}</div>`;
  content.querySelectorAll('.genre-card').forEach(card => {
    card.onclick = () => { state.drillTarget = { type: 'genre', value: card.dataset.genre }; renderView(); };
  });
}"""
GENRE_NEW = """function renderGenreView() {
  if (state.drillTarget) {
    if (state.drillTarget.type === 'genre') { renderGenreAlbums(state.drillTarget.value); return; }
    // An album/compilation/DJ mix opened from within a genre: show its tracks,
    // with the back button returning to that genre's album grid.
    const g = state.drillTarget.fromGenre;
    renderTrackList(getVisibleTracks(), () => {
      state.drillTarget = { type: 'genre', value: g };
      renderView();
    }, g || 'Genres');
    return;
  }
  const content = document.getElementById('content');
  ensureIndexes();
  const map = {};   // genre -> Set of album names
  for (const t of state.tracks) {
    if (!map[t.genre]) map[t.genre] = new Set();
    map[t.genre].add(t.album);
  }
  const colors = ['#d4181b','#1932a0','#f5c518','#d4181b','#f5f3ee','#1932a0','#d4181b','#f5c518','#1932a0','#d4181b'];
  const textColors = ['#fff','#fff','#0d0d0d','#fff','#0d0d0d','#fff','#fff','#0d0d0d','#fff','#fff'];
  const cards = Object.entries(map).sort((a,b) => b[1].size - a[1].size).map(([name, set], i) => {
    const c = colors[i % colors.length];
    const tc = textColors[i % textColors.length];
    const n = set.size;
    return `
    <div class="genre-card" data-genre="${esc(name)}" style="background:${c}">
      <div class="genre-name" style="color:${tc}">${esc(name || 'Unknown')}</div>
      <div class="genre-count" style="color:${tc};opacity:0.7">${n} album${n !== 1 ? 's' : ''}</div>
    </div>`;
  }).join('');
  content.innerHTML = `
    <div class="section-header"><span class="section-title">Genres</span><span class="section-count">${Object.keys(map).length} genres</span></div>
    <div class="genre-grid">${cards}</div>`;
  content.querySelectorAll('.genre-card').forEach(card => {
    card.onclick = () => { state.drillTarget = { type: 'genre', value: card.dataset.genre }; renderView(); };
  });
}

function renderGenreAlbums(genre) {
  const content = document.getElementById('content');
  ensureIndexes();
  const idx = state.indexes || {};
  const tba = idx.tracksByAlbum || {};
  const inGenre = (albumName) => (tba[albumName] || []).some(t => t.genre === genre);
  const entries = [];
  for (const a of Object.values(idx.albums || {}))       if (inGenre(a.album)) entries.push({ album: a.album, artist: a.artist, seed: a.seed, artUrl: a.artUrl, _type: 'album' });
  for (const c of Object.values(idx.compilations || {})) if (inGenre(c.album)) entries.push({ album: c.album, artist: 'Various Artists', seed: c.seed, artUrl: c.artUrl, _type: 'compilation' });
  for (const d of Object.values(idx.djmixes || {}))      if (inGenre(d.album)) entries.push({ album: d.album, artist: d.artist, seed: d.seed, artUrl: d.artUrl, _type: 'djmix' });
  entries.sort((a, b) => a.album.localeCompare(b.album));
  const cards = entries.map(info => `
    <div class="grid-card" data-album="${esc(info.album)}" data-artist="${esc(info.artist || '')}" data-type="${info._type}">
      <div class="card-art"><canvas class="art-canvas" data-seed="${esc(info.seed)}" data-arturl="${esc(info.artUrl || '')}" data-size="160"></canvas></div>
      <div class="card-label">${esc(info.album)}</div>
      <div class="card-sublabel"><span class="clickable-artist" data-artist="${esc(info.artist || '')}">${esc(info.artist || '')}</span></div>
    </div>`).join('');
  content.innerHTML = `
    <button class="back-btn" id="genre-back-btn">
      <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"/></svg>
      Genres
    </button>
    <div class="section-header"><span class="section-title">${esc(genre || 'Unknown')}</span><span class="section-count">${entries.length} album${entries.length !== 1 ? 's' : ''}</span></div>
    <div class="grid-view">${cards || '<div style="padding:24px;color:var(--text3);font-size:13px">No albums in this genre</div>'}</div>`;
  initArtCanvases();
  document.getElementById('genre-back-btn').onclick = () => { state.drillTarget = null; renderView(); };
  content.querySelectorAll('.grid-card').forEach(card => {
    card.onclick = () => {
      state.drillTarget = { type: card.dataset.type, value: card.dataset.album, artist: card.dataset.artist, fromGenre: genre };
      renderView();
    };
  });
}"""

# ── 7. Album hero: insert Add to Playlist button after Play ────────────────────
HERO_OLD = """        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <button class="play-all-btn" id="play-all-btn">
            <svg width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            Play
          </button>"""
HERO_NEW = """        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <button class="play-all-btn" id="play-all-btn">
            <svg width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            Play
          </button>
          <button class="add-album-btn" id="add-album-btn">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Add to Playlist
          </button>"""

# ── 8. renderTrackList: wire the add-album button ──────────────────────────────
WIRE_OLD = """  if (document.getElementById('save-all-btn')) {
    document.getElementById('save-all-btn').onclick = () => saveCollectionToDevice(tracks, title);
  }"""
WIRE_NEW = """  if (document.getElementById('save-all-btn')) {
    document.getElementById('save-all-btn').onclick = () => saveCollectionToDevice(tracks, title);
  }
  if (document.getElementById('add-album-btn')) {
    document.getElementById('add-album-btn').onclick = (e) => {
      pendingAddTrackIds = tracks.map(t => t.id);
      const r = e.currentTarget.getBoundingClientRect();
      showCtxMenu(r.left, r.bottom + 4, 'add-album-to-playlist');
    };
  }"""

OPS = [
    ("shuffle/repeat + add-album CSS", CSS_OLD, CSS_NEW),
    ("pendingAddTrackIds global", PENDING_OLD, PENDING_NEW),
    ("addTracksToJellyfinPlaylist helper", ADDTRACK_OLD, ADDTRACK_NEW),
    ("modal new-with-tracks branch", MODAL_OLD, MODAL_NEW),
    ("ctx add-album-to-playlist branch", CTX_OLD, CTX_NEW),
    ("renderGenreView by album", GENRE_OLD, GENRE_NEW),
    ("album hero Add to Playlist button", HERO_OLD, HERO_NEW),
    ("wire add-album button", WIRE_OLD, WIRE_NEW),
]


def die(msg):
    print(f"ERROR: {msg}")
    sys.exit(1)


def main():
    if not TARGET.exists():
        die(f"{TARGET} not found. Run from the repo root.")

    raw = TARGET.read_bytes()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8").replace("\r\n", "\n")

    if "function renderGenreAlbums" in text:
        print("Already applied (renderGenreAlbums present). Nothing to do.")
        return

    # Verify all anchors unique before touching anything.
    for label, old, _ in OPS:
        n = text.count(old)
        if n == 0:
            die(f"anchor not found: {label}")
        if n > 1:
            die(f"anchor not unique ({n} matches): {label}")

    for _, old, new in OPS:
        text = text.replace(old, new)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = TARGET.with_name(f"{TARGET.name}.backup-{stamp}")
    backup.write_bytes(raw)

    out = text.replace("\n", nl) if nl == "\r\n" else text
    TARGET.write_bytes(out.encode("utf-8"))

    print(f"Patched {TARGET}")
    print(f"Backup written to {backup.name}")
    print("Applied:", ", ".join(label for label, _, _ in OPS))


if __name__ == "__main__":
    main()
