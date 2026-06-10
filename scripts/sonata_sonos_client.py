#!/usr/bin/env python3
# scripts/sonata_sonos_client.py
# ============================================================
# Reconciles Sonata's existing client-side Sonos cast layer with
# the new bridge endpoints, and wires the local transport buttons
# to follow the cast so play/pause/next/prev on every surface
# control the speaker while a room is active.
#
# Bridge shape changes this adapts to:
#   - discovery:  GET /rooms {rooms:[{id,name}]}  ->  GET /sonos {players:[{host,name}]}
#   - play:       POST /play {roomId,streamUrl}   ->  POST /sonos/play {host, ids:[...]}
#   - stop:       POST /stop {roomId}             ->  POST /sonos/pause {host}
#   - transport:  (none)                          ->  /sonos/pause|resume|next|previous {host}
#   - auth:       none                            ->  none needed on the LAN (bridge bypasses
#                                                     the key for private addresses)
#   - URL build:  client sent bare streamUrl      ->  bridge builds LAN .mp3 URL from item id
#
# Internally we keep the existing "room" object shape {id,name} by
# mapping each bridge player to {id: host, name: name||host}, so
# renderSonosRooms and the toggle handler change as little as
# possible. speaker.activeRoom.id therefore holds the host (IP).
#
# Conventions, matching the other client patchers:
#   - run from the repo root, not from scripts/
#   - idempotent: re-running is a no-op
#   - timestamped backup before writing
#   - fails loud if any anchor is missing or not unique
#   - aborts before writing if any replacement would not apply
#   - LF anchors (read_text normalises CRLF to LF in memory)
# ============================================================

import sys
from datetime import datetime
from pathlib import Path

HTML = Path('sonata-pwa.html')
MARKER = '/* sonata-sonos-client-reconciled */'

# Each entry: (description, old, new). old must appear exactly once.
EDITS = []

# ---- 1. discoverSonosRooms: GET /sonos, map players -> rooms ----
EDITS.append((
    'discoverSonosRooms uses /sonos and maps players to rooms',
    """    const data = await bridgeGet('/rooms');
    speaker.sonosRooms = data.rooms || [];
    renderSonosRooms();""",
    """    const data = await bridgeGet('/sonos');
    // Bridge returns { players:[{host,name}] }. Map to the room shape
    // the rest of the cast UI expects: id holds the host (IP).
    speaker.sonosRooms = (data.players || []).map(p => ({
      id:   p.host,
      name: p.name || p.host,
    }));
    renderSonosRooms();"""
))

# ---- 2. playSonos: POST /sonos/play with host + item ids --------
# Replace the whole bridgePost block inside playSonos. The speaker
# now gets the queue from the current track onward so next/prev have
# somewhere to go, and the bridge builds the .mp3 URLs from the ids.
EDITS.append((
    'playSonos posts host + ids to /sonos/play',
    """  speaker.activeRoom = room;
  audio.pause();

  const streamUrl = state.currentTrack.streamUrl || null;

  try {
    await bridgePost('/play', {
      roomId:    room.id,
      streamUrl, // Jellyfin direct stream URL — Sonos pulls audio itself
      title:     state.currentTrack.title,
      artist:    state.currentTrack.artist,
    });
    speaker.sonosPlaying = true;
    updateCastBtns();
    showToast(`Playing on ${room.name}`);
    renderSonosRooms();
  } catch(e) {
    speaker.activeRoom = null;
    showToast('Could not reach Sonos bridge');
    renderSonosRooms();
  }""",
    """  speaker.activeRoom = room;
  // Stop local audio (use the real element, not pausePlayback, so we
  // don't kick off the silent-loop machinery while casting).
  audio.pause();

  // Build the list of Jellyfin item ids from the current queue, from
  // the current position onward, so the speaker queue mirrors what
  // would have played locally. The bridge turns each id into a LAN
  // .mp3 stream URL itself.
  const ids = sonosQueueIds();

  try {
    await bridgePost('/sonos/play', { host: room.id, ids });
    speaker.sonosPlaying = true;
    updateCastBtns();
    showToast(`Playing on ${room.name}`);
    renderSonosRooms();
  } catch(e) {
    speaker.activeRoom = null;
    showToast('Could not reach Sonos bridge');
    renderSonosRooms();
  }"""
))

# ---- 3. stopSonos: POST /sonos/pause -------------------------
EDITS.append((
    'stopSonos posts to /sonos/pause',
    """  try { await bridgePost('/stop', { roomId: speaker.activeRoom.id }); } catch(e) {}
  speaker.activeRoom   = null;
  speaker.sonosPlaying = false;
  updateCastBtns();
  renderSonosRooms();
  showToast('Stopped Sonos');""",
    """  try { await bridgePost('/sonos/pause', { host: speaker.activeRoom.id }); } catch(e) {}
  speaker.activeRoom   = null;
  speaker.sonosPlaying = false;
  updateCastBtns();
  renderSonosRooms();
  showToast('Stopped Sonos');"""
))

# ---- 4a. Helpers: inject a standalone block before playSonos ----
EDITS.append((
    'inject cast helpers before playSonos',
    """async function playSonos(room) {""",
    """// ── Cast helpers ───────────────────────────────────────────────
""" + MARKER + """
function isCasting() { return !!(speaker && speaker.activeRoom); }

// Item ids for the current queue, from the current position onward.
// Falls back to just the current track if the queue isn't populated.
function sonosQueueIds() {
  try {
    if (Array.isArray(state.queue) && state._queueTracks && state.queue.length) {
      return state.queue
        .slice(state.queuePos)
        .map(i => state._queueTracks[i])
        .filter(Boolean)
        .map(t => t.jellyfinId || t.id)
        .filter(Boolean);
    }
  } catch (e) {}
  const t = state.currentTrack;
  const id = t && (t.jellyfinId || t.id);
  return id ? [id] : [];
}

async function sonosControl(path) {
  if (!isCasting()) return;
  try { await bridgePost(path, { host: speaker.activeRoom.id }); }
  catch (e) { showToast('Sonos control failed'); }
}

async function playSonos(room) {"""
))

# ---- 4b. Redirect: inject a guard at the TOP of each transport fn.
# Done by editing the function bodies in place (not reassigning the
# names afterward), because some buttons capture togglePlay/prevTrack/
# nextTrack by reference at wiring time, before any later reassignment
# would run. Editing the body means the captured reference is already
# the guarded version. When casting, route to the speaker and return;
# otherwise fall through to the original local behaviour.
EDITS.append((
    'redirect togglePlay to Sonos when casting',
    """function togglePlay() {
  if (!state.currentTrack) return;
  state.playing ? pausePlayback() : resumePlayback();
}""",
    """function togglePlay() {
  if (isCasting()) {
    if (speaker.sonosPlaying) { sonosControl('/sonos/pause'); speaker.sonosPlaying = false; }
    else { sonosControl('/sonos/resume'); speaker.sonosPlaying = true; }
    updateAllPlayerUIs();
    return;
  }
  if (!state.currentTrack) return;
  state.playing ? pausePlayback() : resumePlayback();
}"""
))

EDITS.append((
    'redirect prevTrack to Sonos when casting',
    """function prevTrack() {
  if (audio.currentTime > 3) { audio.currentTime = 0; return; }
  state.queuePos = Math.max(0, state.queuePos - 1);
  playCurrentQueue(); renderView();
}""",
    """function prevTrack() {
  if (isCasting()) { sonosControl('/sonos/previous'); return; }
  if (audio.currentTime > 3) { audio.currentTime = 0; return; }
  state.queuePos = Math.max(0, state.queuePos - 1);
  playCurrentQueue(); renderView();
}"""
))

EDITS.append((
    'redirect nextTrack to Sonos when casting',
    """function nextTrack() {
  state.queuePos = Math.min(state.queue.length-1, state.queuePos+1);
  if (state.queuePos < state.queue.length) { playCurrentQueue(); renderView(); }
}""",
    """function nextTrack() {
  if (isCasting()) { sonosControl('/sonos/next'); return; }
  state.queuePos = Math.min(state.queue.length-1, state.queuePos+1);
  if (state.queuePos < state.queue.length) { playCurrentQueue(); renderView(); }
}"""
))


def fail(msg):
    print(f"ABORT: {msg}")
    sys.exit(1)


def main():
    if not HTML.exists():
        fail(f"{HTML} not found. Run from the repo root.")

    text = HTML.read_text(encoding='utf-8')

    if MARKER in text:
        print("Already reconciled (marker present). Nothing to do.")
        return

    # Pre-flight: every anchor must be present exactly once.
    for desc, old, _new in EDITS:
        n = text.count(old)
        if n == 0:
            fail(f"anchor not found for: {desc}")
        if n > 1:
            fail(f"anchor not unique ({n} matches) for: {desc}")

    # The three transport functions must each be a single declaration,
    # since we inject a guard clause into each body. (We edit bodies in
    # place rather than reassigning the names, so buttons that captured
    # the reference at wiring time get the guarded version.)
    for fn in ['function togglePlay(', 'function prevTrack(', 'function nextTrack(']:
        if text.count(fn) != 1:
            fail(f"expected exactly one declaration of {fn!r}")

    # Apply.
    new_text = text
    for desc, old, new in EDITS:
        new_text = new_text.replace(old, new, 1)

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = HTML.with_suffix(f'.backup-{stamp}.html')
    backup.write_text(text, encoding='utf-8')
    print(f"Backup written: {backup}")

    HTML.write_text(new_text, encoding='utf-8')
    print("Reconciled Sonata cast layer with the new bridge endpoints.")
    print("Applied:")
    for desc, _o, _n in EDITS:
        print(f"  - {desc}")
    print("Deploy: commit, push, then hard-reload desktop (Ctrl+F5).")


if __name__ == '__main__':
    main()
