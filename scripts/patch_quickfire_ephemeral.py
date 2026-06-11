#!/usr/bin/env python3
r"""
patch_quickfire_ephemeral.py

Makes Quickfires ephemeral instead of permanent playlists.

Before: each Quickfire created a Jellyfin playlist that lived in the playlist
list forever, so they piled up and got forgotten.

After:
  - A Quickfire is a today-only item stored client-side (never uploaded to
    Jellyfin). It is named "Quickfire 1", "Quickfire 2" and so on for the day.
  - The listening day rolls at 3am, so quickfires made late evening or after
    midnight still count as that night and clear at the following 3am. They are
    pruned on load and on render. No accumulation.
  - They appear in a "Today's Quickfires" section on the home screen, below the
    Quickfire button and above the 12 picks. Tap one to play it.
  - Each has a "Save as playlist" button that promotes it to a proper playlist
    (created on Jellyfin if connected, date-stamped), after which it leaves the
    ephemeral section and behaves like any normal playlist.

The old createQuickfirePlaylist tail is rewritten; nextQuickfireName becomes
unused (left in place, harmless) since names are now computed against the
ephemeral store.

Touches the Quickfire helpers, createQuickfirePlaylist, and renderHome. Safe to
run repeatedly: idempotent on the marker 'sonata-quickfire-ephemeral'. Creates a
timestamped backup. Fails loudly if any anchor is missing or ambiguous.

Run from the repo root:
    cd C:\Users\peter\repos\sonata
    python scripts\patch_quickfire_ephemeral.py
"""

import sys
import datetime
from pathlib import Path

TARGET = Path("sonata-pwa.html")
MARKER = "sonata-quickfire-ephemeral"


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


# ---- 1. Helper functions, injected before startQuickfireSelection ----
HELPERS = r"""// sonata-quickfire-ephemeral: today-only quickfires that vanish at 3am, plus
// promotion to a permanent playlist. Stored client-side, never uploaded to
// Jellyfin (the playlist sync preserves local-only entries anyway).
const QUICKFIRE_KEY = 'sonata_quickfires';

function quickfireDayKey() {
  // Listening day rolls at 3am: anything before 3am counts as the night before.
  const d = new Date(Date.now() - 3 * 60 * 60 * 1000);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function loadQuickfires() {
  try {
    const raw = localStorage.getItem(QUICKFIRE_KEY);
    if (!raw) return [];
    const data = JSON.parse(raw);
    if (!data || data.day !== quickfireDayKey()) return [];   // rolled past 3am
    return Array.isArray(data.items) ? data.items : [];
  } catch (e) { return []; }
}

function saveQuickfires() {
  try {
    localStorage.setItem(QUICKFIRE_KEY, JSON.stringify({ day: quickfireDayKey(), items: state.quickfires }));
  } catch (e) { /* quota, non-fatal */ }
}

// Hydrate state.quickfires from storage, auto-pruning anything from before the
// last 3am rollover.
function refreshQuickfires() {
  state.quickfires = loadQuickfires();
  return state.quickfires;
}

function playQuickfire(qfId) {
  refreshQuickfires();
  const qf = state.quickfires.find(q => q.id === qfId);
  if (!qf) { showToast('That quickfire has expired'); renderView(); return; }
  const tracks = qf.trackIds.map(id => state.tracks.find(t => t.id === id)).filter(Boolean);
  if (!tracks.length) { showToast('Quickfire tracks unavailable'); return; }
  playTracksAt(tracks, 0);
  showToast(`Playing ${qf.name} (${tracks.length} tracks)`);
}

async function promoteQuickfire(qfId) {
  refreshQuickfires();
  const qf = state.quickfires.find(q => q.id === qfId);
  if (!qf) { showToast('That quickfire has expired'); renderView(); return; }
  const tracks = qf.trackIds.map(id => state.tracks.find(t => t.id === id)).filter(Boolean);
  if (!tracks.length) { showToast('No tracks to save'); return; }

  const d = new Date();
  const name = `${d.getDate()}/${d.getMonth() + 1} ${qf.name}`;
  const pl = await createJellyfinPlaylist(name);
  pl.trackIds = tracks.map(t => t.id);

  if (jellyfin.connected && pl.id && !/^[0-9]{13}$/.test(pl.id)) {
    try {
      const ids = tracks.map(t => t.id).join(',');
      await jfPost(`/Playlists/${pl.id}/Items?Ids=${ids}&UserId=${jellyfin.userId}`, {});
      const items = await jfGet(`/Playlists/${pl.id}/Items?UserId=${jellyfin.userId}`);
      pl._entryIds = {};
      for (const i of (items.Items || [])) pl._entryIds[i.Id] = i.PlaylistItemId;
    } catch (e) {
      console.warn('Quickfire promote bulk-add failed:', e);
    }
  }

  state.playlists.push(pl);
  savePlaylists();
  renderPlaylists();

  state.quickfires = state.quickfires.filter(q => q.id !== qfId);
  saveQuickfires();

  showToast(`Saved as "${name}"`);
  renderView();
}

function startQuickfireSelection() {"""


# ---- 2. createQuickfirePlaylist tail ----
TAIL_OLD = """  const name = nextQuickfireName();

  // Exit selection mode immediately so the UI feels responsive
  state.quickfireMode = false;
  state.quickfireSelected = [];

  // Create the playlist (Jellyfin or local-only fallback)
  const pl = await createJellyfinPlaylist(name);
  pl.trackIds = allTracks.map(t => t.id);

  // Bulk-add to Jellyfin if connected. Single call with comma-separated IDs.
  if (jellyfin.connected && pl.id && !/^[0-9]{13}$/.test(pl.id)) {
    try {
      const ids = allTracks.map(t => t.id).join(',');
      await jfPost(`/Playlists/${pl.id}/Items?Ids=${ids}&UserId=${jellyfin.userId}`, {});
      // Refresh entry IDs for delete-track-from-playlist support later
      const items = await jfGet(`/Playlists/${pl.id}/Items?UserId=${jellyfin.userId}`);
      pl._entryIds = {};
      for (const i of (items.Items || [])) {
        pl._entryIds[i.Id] = i.PlaylistItemId;
      }
    } catch(e) {
      console.warn('Quickfire bulk-add failed, playlist created but empty server-side:', e);
    }
  }

  state.playlists.push(pl);
  savePlaylists();
  renderPlaylists();

  // Start playback from the shuffled track order
  playTracksAt(allTracks, 0);
  showToast(`${name} \u2014 playing ${allTracks.length} tracks`);

  // Route into the playlist's track view so the user can see what they made
  state.currentView = 'playlist';
  state.drillTarget = { type: 'playlist', value: pl.id };
  // Sync nav highlighting so the active state lines up with the new view
  document.querySelectorAll('.nav-item[data-view]').forEach(n => n.classList.remove('active'));
  document.querySelectorAll('.bnav-item').forEach(n => n.classList.toggle('active', n.dataset.view === 'playlists-mobile'));
  renderView();
}"""

TAIL_NEW = r"""  refreshQuickfires();
  let _qfMax = 0;
  for (const q of state.quickfires) {
    const mm = (q.name || '').match(/^Quickfire (\d+)$/);
    if (mm) { const v = parseInt(mm[1], 10); if (v > _qfMax) _qfMax = v; }
  }
  const name = `Quickfire ${_qfMax + 1}`;

  // Exit selection mode immediately so the UI feels responsive.
  state.quickfireMode = false;
  state.quickfireSelected = [];

  // Ephemeral: store as a today-only quickfire, not a Jellyfin playlist.
  const qf = { id: 'qf' + Date.now(), name, trackIds: allTracks.map(t => t.id) };
  state.quickfires.push(qf);
  saveQuickfires();

  // Play the shuffled order straight away.
  playTracksAt(allTracks, 0);
  showToast(`Playing ${name} (${allTracks.length} tracks)`);

  // Land on Home, where the new quickfire now sits under Today's Quickfires.
  setView('home');
}"""


# ---- 4a. renderHome: build the Today's Quickfires section ----
HOME_A_OLD = """  content.innerHTML = `
    <div class="home-hero">"""

HOME_A_NEW = r"""  refreshQuickfires();
  const quickfiresSection = (!inSelect && state.quickfires.length) ? `
    <div class="home-section-bar"><span class="home-section-title">Today's Quickfires</span></div>
    <div style="display:flex;flex-direction:column;gap:8px;padding:0 18px 6px">
      ${state.quickfires.map(qf => `
        <div class="qf-today-row" data-qf="${esc(qf.id)}" style="display:flex;align-items:center;gap:12px;padding:10px 14px;border:2px solid var(--border);background:var(--surface2);cursor:pointer">
          <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24" style="flex-shrink:0"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          <div style="flex:1;min-width:0">
            <div style="font-weight:700">${esc(qf.name)}</div>
            <div style="font-size:11px;color:var(--text3);font-family:'IBM Plex Mono',monospace">${qf.trackIds.length} track${qf.trackIds.length !== 1 ? 's' : ''}</div>
          </div>
          <button class="home-reshuffle qf-save-btn" data-qf="${esc(qf.id)}">Save as playlist</button>
        </div>`).join('')}
    </div>` : '';

  content.innerHTML = `
    <div class="home-hero">"""


# ---- 4b. renderHome: place the section in the template ----
HOME_B_OLD = """    </div>
    ${qfBar}"""

HOME_B_NEW = """    </div>
    ${quickfiresSection}
    ${qfBar}"""


# ---- 5. renderHome: wire the quickfire row + save handlers ----
HOME_C_OLD = """  content.querySelectorAll('.home-album-card').forEach(card => {"""

HOME_C_NEW = """  content.querySelectorAll('.qf-today-row').forEach(row => {
    row.onclick = (e) => {
      if (e.target.closest('.qf-save-btn')) return;
      playQuickfire(row.dataset.qf);
    };
  });
  content.querySelectorAll('.qf-save-btn').forEach(btn => {
    btn.onclick = (e) => { e.stopPropagation(); promoteQuickfire(btn.dataset.qf); };
  });

  content.querySelectorAll('.home-album-card').forEach(card => {"""


def main():
    if not TARGET.exists():
        die("%s not found. Run from the repo root." % TARGET)

    text = TARGET.read_text(encoding="utf-8")  # CRLF -> LF in memory on Windows

    if MARKER in text:
        print("Already patched (marker present). Nothing to do.")
        return

    text = apply(text, "function startQuickfireSelection() {", HELPERS, "quickfire helpers")
    text = apply(text, TAIL_OLD, TAIL_NEW, "createQuickfirePlaylist tail")
    text = apply(text, HOME_A_OLD, HOME_A_NEW, "renderHome section build")
    text = apply(text, HOME_B_OLD, HOME_B_NEW, "renderHome section placement")
    text = apply(text, HOME_C_OLD, HOME_C_NEW, "renderHome handlers")

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = TARGET.with_name(TARGET.name + ".bak-" + stamp)
    backup.write_bytes(TARGET.read_bytes())
    TARGET.write_text(text, encoding="utf-8")  # \n -> CRLF on Windows

    print("Patched %s" % TARGET)
    print("Backup  %s" % backup)


if __name__ == "__main__":
    main()
