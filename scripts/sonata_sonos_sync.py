#!/usr/bin/env python3
# scripts/sonata_sonos_sync.py
# ============================================================
# Makes the player reflect and fully control a Sonos cast.
#
# After the cast-reconciliation patch, casting played on the
# speaker and the transport buttons controlled it, but the app's
# own display was blind to the cast: the now-playing bar showed
# nothing, the track highlight stayed on the paused first track
# when you skipped, and the volume slider moved local volume the
# speaker never heard.
#
# This patch closes that gap, with an EXPLICIT casting state (the
# bar shows "Casting to <room>" rather than pretending playback is
# local). Four changes:
#
#   1. playSonos: set state.currentTrack + queue position to the
#      track being cast, refresh the UI, and show the cast banner.
#   2. next/prev redirects: advance state.queuePos locally in step
#      with the speaker, set the new currentTrack, refresh UI, so
#      the highlighted track follows.
#   3. setVolume: when casting, send the scaled (0..100) level to
#      the speaker via /sonos/volume.
#   4. stopSonos: clear the cast banner, restore normal display.
#
# sonosControl is extended to carry an optional body payload so the
# volume level can ride along (transport calls still send just host).
#
# Depends on the cast-reconciliation patch (marker
# sonata-sonos-client-reconciled) being present. Aborts if not.
#
# Conventions: run from repo root, idempotent, timestamped backup,
# fails loud on missing/non-unique anchors, LF anchors.
# ============================================================

import sys
from datetime import datetime
from pathlib import Path

HTML = Path('sonata-pwa.html')
MARKER = '/* sonata-sonos-sync */'
DEP_MARKER = '/* sonata-sonos-client-reconciled */'

EDITS = []

# ---- 0. Harden isCasting against TDZ: it may be called at load
# (via setVolume(0.8)) before `speaker` (a const declared later in
# the file) is initialised. Touching a const in its temporal dead
# zone throws ReferenceError, even via typeof. A try/catch is the
# only fully safe guard. Replace the one-line body installed by the
# reconciliation patch with a safe version.
EDITS.append((
    'harden isCasting against load-time access before speaker exists',
    """function isCasting() { return !!(speaker && speaker.activeRoom); }""",
    """function isCasting() {
  try { return !!(speaker && speaker.activeRoom); }
  catch (e) { return false; }  // speaker not yet initialised (load-time call)
}"""
))

# ---- 1. Extend sonosControl to take an optional body ------------
EDITS.append((
    'sonosControl accepts an optional extra body (for volume level)',
    """async function sonosControl(path) {
  if (!isCasting()) return;
  try { await bridgePost(path, { host: speaker.activeRoom.id }); }
  catch (e) { showToast('Sonos control failed'); }
}""",
    MARKER + """
async function sonosControl(path, extra) {
  if (!isCasting()) return;
  const body = Object.assign({ host: speaker.activeRoom.id }, extra || {});
  try { await bridgePost(path, body); }
  catch (e) { showToast('Sonos control failed'); }
}

// Show / hide an explicit "Casting to <room>" banner on the now-
// playing surfaces. We deliberately do not disguise a cast as local
// playback: the bar says where the sound is going.
function setCastIndicator(on) {
  const room = (speaker.activeRoom && speaker.activeRoom.name) || 'speaker';
  const npArtist   = document.getElementById('np-artist');
  const miniArtist = document.getElementById('mini-artist');
  const fpArtist   = document.getElementById('fp-artist');
  if (on) {
    const label = `Casting to ${room}`;
    if (npArtist)   npArtist.dataset.cast   = label;
    if (miniArtist) miniArtist.dataset.cast = label;
    if (fpArtist)   fpArtist.dataset.cast   = label;
  } else {
    [npArtist, miniArtist, fpArtist].forEach(el => { if (el) delete el.dataset.cast; });
  }
}

// Point the local player state at a track object without touching
// the local audio element (used while casting, so the display
// follows the speaker). Then refresh the UI and re-assert the cast
// banner, since updateAllPlayerUIs rewrites the artist line.
function reflectCastTrack(track) {
  if (!track) return;
  state.currentTrack = track;
  state.playing = true;
  updateAllPlayerUIs();
  renderPlayingState();
  // Re-apply the banner: updateAllPlayerUIs has just set the artist
  // line to the real artist, so append the cast label after it.
  const room = (speaker.activeRoom && speaker.activeRoom.name) || 'speaker';
  ['np-artist','mini-artist','fp-artist'].forEach(id => {
    const el = document.getElementById(id);
    if (el && track.artist) el.textContent = `${track.artist} · Casting to ${room}`;
    else if (el) el.textContent = `Casting to ${room}`;
  });
}"""
))

# ---- 2. playSonos: reflect the cast track + show banner ---------
# After the successful bridgePost, sync the display to the first
# cast track. The current track is whatever sonosQueueIds started
# from, i.e. state.currentTrack already (the queue head). Reflect it.
EDITS.append((
    'playSonos reflects the cast track in the display',
    """    await bridgePost('/sonos/play', { host: room.id, ids });
    speaker.sonosPlaying = true;
    updateCastBtns();
    showToast(`Playing on ${room.name}`);
    renderSonosRooms();""",
    """    await bridgePost('/sonos/play', { host: room.id, ids });
    speaker.sonosPlaying = true;
    updateCastBtns();
    showToast(`Playing on ${room.name}`);
    renderSonosRooms();
    // Reflect the cast in the player display (explicit cast banner).
    setCastIndicator(true);
    reflectCastTrack(state.currentTrack);"""
))

# ---- 3. next/prev redirects advance local state in step ---------
# Replace the bare redirect lines (added by the reconciliation
# patch) with versions that also move state.queuePos and reflect the
# new track, so the highlighted track follows the speaker.
EDITS.append((
    'nextTrack redirect advances local queue position',
    """  if (isCasting()) { sonosControl('/sonos/next'); return; }""",
    """  if (isCasting()) {
    sonosControl('/sonos/next');
    // Mirror the advance locally so the display follows the speaker.
    if (state.queuePos < state.queue.length - 1) {
      state.queuePos++;
      reflectCastTrack(state._queueTracks[state.queue[state.queuePos]]);
    }
    return;
  }"""
))

EDITS.append((
    'prevTrack redirect steps local queue position back',
    """  if (isCasting()) { sonosControl('/sonos/previous'); return; }""",
    """  if (isCasting()) {
    sonosControl('/sonos/previous');
    if (state.queuePos > 0) {
      state.queuePos--;
      reflectCastTrack(state._queueTracks[state.queue[state.queuePos]]);
    }
    return;
  }"""
))

# ---- 4. setVolume sends to the speaker when casting -------------
# Inject after the local volume has been applied and the fill UI
# updated. Anchor on the two fill-width lines that end the visual
# update inside setVolume.
EDITS.append((
    'setVolume routes to the speaker when casting',
    """  document.getElementById('vol-fill').style.width = v;
  document.getElementById('fp-vol-fill').style.width = v;""",
    """  document.getElementById('vol-fill').style.width = v;
  document.getElementById('fp-vol-fill').style.width = v;
  // While casting, drive the speaker volume too (bridge wants 0..100).
  // Wrapped: setVolume(0.8) runs at load before `speaker` (a const
  // declared later) exists, and touching it then throws a TDZ error.
  // The try/catch makes the early call a harmless no-op.
  try {
    if (speaker && speaker.activeRoom) {
      sonosControl('/sonos/volume', { level: Math.round(state.volume * 100) });
    }
  } catch (e) { /* speaker not initialised yet (load-time call) */ }"""
))

# ---- 5. stopSonos clears the banner -----------------------------
EDITS.append((
    'stopSonos clears the cast indicator',
    """  speaker.activeRoom   = null;
  speaker.sonosPlaying = false;
  updateCastBtns();
  renderSonosRooms();
  showToast('Stopped Sonos');""",
    """  speaker.activeRoom   = null;
  speaker.sonosPlaying = false;
  updateCastBtns();
  renderSonosRooms();
  setCastIndicator(false);
  state.playing = false;
  updateAllPlayerUIs();
  showToast('Stopped Sonos');"""
))


def fail(msg):
    print(f"ABORT: {msg}")
    sys.exit(1)


def main():
    if not HTML.exists():
        fail(f"{HTML} not found. Run from the repo root.")

    text = HTML.read_text(encoding='utf-8')

    if MARKER in text:
        print("Already applied (marker present). Nothing to do.")
        return

    if DEP_MARKER not in text:
        fail("dependency missing: the cast-reconciliation patch "
             "(sonata_sonos_client.py) must be applied first.")

    for desc, old, _new in EDITS:
        n = text.count(old)
        if n == 0:
            fail(f"anchor not found for: {desc}")
        if n > 1:
            fail(f"anchor not unique ({n} matches) for: {desc}")

    new_text = text
    for _desc, old, new in EDITS:
        new_text = new_text.replace(old, new, 1)

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = HTML.with_suffix(f'.backup-{stamp}.html')
    backup.write_text(text, encoding='utf-8')
    print(f"Backup written: {backup}")

    HTML.write_text(new_text, encoding='utf-8')
    print("Synced player display and volume with Sonos casting.")
    for desc, _o, _n in EDITS:
        print(f"  - {desc}")
    print("Deploy: commit, push, hard-reload desktop (Ctrl+F5).")


if __name__ == '__main__':
    main()
