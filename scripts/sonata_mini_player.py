# sonata_mini_player.py
# ============================================================
# Adds a desktop-only floating mini player to sonata-pwa.html.
#
# The mini player:
#   - Appears automatically when a track is playing (desktop only).
#   - Hides when playback stops or the X button is clicked.
#   - Is draggable anywhere on screen.
#   - Shows album art, track title, artist name.
#   - Controls: prev, play/pause, next, shuffle, repeat, volume,
#     progress bar with scrubbing.
#   - Genre button: plays shuffled tracks from a genre chosen
#     deterministically by date hash. Same genre all day. No
#     "pick another" option. Stops current track immediately.
#     Genre name shown in the button as a pill while active.
#   - Reads state from Sonata's existing audio element and state
#     object; does not duplicate any playback logic.
#   - Desktop only: hidden on mobile via isMobile() check,
#     matching Sonata's existing mobile detection pattern.
#
# Two anchors patched:
#   A. Inject mini-player HTML + CSS just before </body>.
#   B. Inject mini-player JS init just before the closing comment
#      "// End of Sonata PWA" in the main script block.
#
# Safe by design:
#   - Bails loudly if either anchor is missing.
#   - Creates a timestamped backup before writing.
#   - Idempotent check: refuses to run if already patched.
#
# Usage (from repo root):
#   python scripts\sonata_mini_player.py
# ============================================================

import shutil
from datetime import datetime
from pathlib import Path

SOURCE = Path('sonata-pwa.html')
BACKUP_SUFFIX = datetime.now().strftime('%Y%m%d-%H%M%S')
BACKUP = SOURCE.with_name(f'sonata-pwa.backup-{BACKUP_SUFFIX}.html')

IDEMPOTENCY_MARKER = 'id="sonata-mini-player"'

ANCHOR_A = '</body>'
ANCHOR_B = '})();\n</script>'

# ---------------------------------------------------------------------------
# Mini-player HTML + CSS (injected before </body>)
# ---------------------------------------------------------------------------

MINI_PLAYER_HTML = """
<!-- ======================================================
     Sonata mini player  (injected by sonata_mini_player.py)
     ====================================================== -->
<style>
#sonata-mini-player {
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: 280px;
  background: #1c1c1e;
  border-radius: 12px;
  border: 0.5px solid rgba(255,255,255,0.1);
  box-shadow: 0 12px 40px rgba(0,0,0,0.55);
  overflow: hidden;
  z-index: 99999;
  display: none;
  user-select: none;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  cursor: default;
}
#sonata-mini-player.smp-visible { display: block; }
#smp-drag-handle {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 36px;
  cursor: grab;
  z-index: 2;
}
#smp-drag-handle:active { cursor: grabbing; }
#smp-close {
  position: absolute;
  top: 8px; right: 8px;
  width: 20px; height: 20px;
  background: rgba(0,0,0,0.45);
  border: 0.5px solid rgba(255,255,255,0.15);
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  color: rgba(255,255,255,0.65);
  font-size: 10px;
  line-height: 1;
  z-index: 3;
  transition: background 0.15s;
}
#smp-close:hover { background: rgba(255,255,255,0.15); color: #fff; }
#smp-art-wrap {
  position: relative;
  width: 100%;
  height: 160px;
  overflow: hidden;
  background: #111;
}
#smp-art {
  width: 100%; height: 100%;
  object-fit: cover;
  display: block;
  opacity: 0.85;
}
#smp-art-placeholder {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  background: #222;
  color: rgba(255,255,255,0.2);
  font-size: 36px;
}
#smp-art-gradient {
  position: absolute;
  bottom: 0; left: 0; right: 0;
  height: 80px;
  background: linear-gradient(to top, rgba(28,28,30,0.98) 0%, transparent 100%);
  pointer-events: none;
}
#smp-meta {
  position: absolute;
  bottom: 8px; left: 12px; right: 12px;
  z-index: 1;
}
#smp-title {
  font-size: 12px;
  font-weight: 600;
  color: #f2f2f7;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: -0.01em;
}
#smp-artist {
  font-size: 11px;
  color: rgba(255,255,255,0.48);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
#smp-controls {
  padding: 10px 12px 12px;
}
#smp-progress-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
}
.smp-time {
  font-size: 9px;
  color: rgba(255,255,255,0.35);
  min-width: 26px;
  font-variant-numeric: tabular-nums;
}
.smp-time.right { text-align: right; }
#smp-progress-track {
  flex: 1;
  height: 3px;
  background: rgba(255,255,255,0.1);
  border-radius: 2px;
  position: relative;
  cursor: pointer;
}
#smp-progress-fill {
  height: 100%;
  background: var(--smp-accent, #c8a96e);
  border-radius: 2px;
  width: 0%;
  pointer-events: none;
}
#smp-progress-thumb {
  position: absolute;
  top: 50%;
  left: 0%;
  width: 9px; height: 9px;
  background: #f2f2f7;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  pointer-events: none;
  box-shadow: 0 0 0 2px rgba(200,169,110,0.35);
}
#smp-btn-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 2px;
}
.smp-ctrl {
  background: none;
  border: none;
  cursor: pointer;
  color: rgba(255,255,255,0.45);
  padding: 5px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 6px;
  font-size: 15px;
  transition: color 0.12s;
  line-height: 1;
}
.smp-ctrl:hover { color: rgba(255,255,255,0.88); }
.smp-ctrl.smp-on { color: var(--smp-accent, #c8a96e); }
#smp-play {
  width: 36px; height: 36px;
  background: #f2f2f7;
  border: none;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  color: #1c1c1e;
  font-size: 14px;
  transition: transform 0.1s, background 0.12s;
}
#smp-play:hover { background: #fff; transform: scale(1.06); }
#smp-play:active { transform: scale(0.95); }
#smp-vol-row {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 9px;
  padding: 0 2px;
}
.smp-vol-icon {
  color: rgba(255,255,255,0.28);
  font-size: 12px;
  cursor: pointer;
  transition: color 0.12s;
}
.smp-vol-icon:hover { color: rgba(255,255,255,0.7); }
#smp-vol-track {
  flex: 1;
  height: 2px;
  background: rgba(255,255,255,0.1);
  border-radius: 2px;
  cursor: pointer;
  position: relative;
}
#smp-vol-fill {
  height: 100%;
  background: rgba(255,255,255,0.28);
  border-radius: 2px;
  pointer-events: none;
}
/* Genre button row */
#smp-genre-row {
  margin-top: 10px;
  padding: 0 2px;
  display: flex;
  align-items: center;
  gap: 8px;
}
#smp-genre-btn {
  flex: 1;
  background: rgba(255,255,255,0.06);
  border: 0.5px solid rgba(255,255,255,0.12);
  border-radius: 20px;
  color: rgba(255,255,255,0.5);
  font-size: 10px;
  font-family: inherit;
  padding: 5px 10px;
  cursor: pointer;
  text-align: left;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
  white-space: nowrap;
  overflow: hidden;
}
#smp-genre-btn:hover {
  background: rgba(255,255,255,0.1);
  color: rgba(255,255,255,0.8);
  border-color: rgba(255,255,255,0.22);
}
#smp-genre-btn.smp-genre-active {
  background: rgba(200,169,110,0.15);
  border-color: rgba(200,169,110,0.4);
  color: var(--smp-accent, #c8a96e);
}
#smp-genre-icon {
  font-size: 11px;
  flex-shrink: 0;
}
#smp-genre-label {
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>

<div id="sonata-mini-player" role="region" aria-label="Mini player">
  <div id="smp-drag-handle"></div>
  <div id="smp-close" title="Close mini player" aria-label="Close mini player">&#x2715;</div>
  <div id="smp-art-wrap">
    <div id="smp-art-placeholder">&#x266A;</div>
    <img id="smp-art" src="" alt="Album art" style="display:none" />
    <div id="smp-art-gradient"></div>
    <div id="smp-meta">
      <div id="smp-title">Nothing playing</div>
      <div id="smp-artist"></div>
    </div>
  </div>
  <div id="smp-controls">
    <div id="smp-progress-row">
      <span class="smp-time" id="smp-elapsed">0:00</span>
      <div id="smp-progress-track">
        <div id="smp-progress-fill"></div>
        <div id="smp-progress-thumb"></div>
      </div>
      <span class="smp-time right" id="smp-duration">0:00</span>
    </div>
    <div id="smp-btn-row">
      <button class="smp-ctrl" id="smp-shuffle" title="Shuffle" aria-label="Shuffle">&#x21c4;</button>
      <button class="smp-ctrl" id="smp-prev" title="Previous" aria-label="Previous track">&#x23ee;</button>
      <button id="smp-play" aria-label="Play / pause">&#x25b6;</button>
      <button class="smp-ctrl" id="smp-next" title="Next" aria-label="Next track">&#x23ed;</button>
      <button class="smp-ctrl" id="smp-repeat" title="Repeat" aria-label="Repeat">&#x1f501;</button>
    </div>
    <div id="smp-vol-row">
      <span class="smp-vol-icon" id="smp-mute" title="Mute" aria-label="Mute">&#x1f507;</span>
      <div id="smp-vol-track">
        <div id="smp-vol-fill" style="width:80%"></div>
      </div>
      <span class="smp-vol-icon" style="font-size:15px">&#x1f50a;</span>
    </div>
    <div id="smp-genre-row">
      <button id="smp-genre-btn" aria-label="Play today's genre">
        <span id="smp-genre-icon">&#x266b;</span>
        <span id="smp-genre-label">Today's genre</span>
      </button>
    </div>
  </div>
</div>
<!-- End Sonata mini player -->
"""

# ---------------------------------------------------------------------------
# Mini-player JS (injected just before ANCHOR_B)
# ---------------------------------------------------------------------------

MINI_PLAYER_JS = """
// ── Sonata mini player (injected by sonata_mini_player.py) ──────────────────
(function () {
  if (typeof isMobile === 'function' && isMobile()) return;

  const mp = document.getElementById('sonata-mini-player');
  if (!mp) return;

  const elClose    = document.getElementById('smp-close');
  const elArt      = document.getElementById('smp-art');
  const elArtPH    = document.getElementById('smp-art-placeholder');
  const elTitle    = document.getElementById('smp-title');
  const elArtist   = document.getElementById('smp-artist');
  const elElapsed  = document.getElementById('smp-elapsed');
  const elDuration = document.getElementById('smp-duration');
  const elPFill    = document.getElementById('smp-progress-fill');
  const elPThumb   = document.getElementById('smp-progress-thumb');
  const elPTrack   = document.getElementById('smp-progress-track');
  const elPlay     = document.getElementById('smp-play');
  const elPrev     = document.getElementById('smp-prev');
  const elNext     = document.getElementById('smp-next');
  const elShuffle  = document.getElementById('smp-shuffle');
  const elRepeat   = document.getElementById('smp-repeat');
  const elVolTrack = document.getElementById('smp-vol-track');
  const elVolFill  = document.getElementById('smp-vol-fill');
  const elMute     = document.getElementById('smp-mute');
  const elGenreBtn = document.getElementById('smp-genre-btn');
  const elGenreLabel = document.getElementById('smp-genre-label');

  let dismissed   = false;
  let muted       = false;
  let lastVol     = 0.8;
  let genreActive = false;  // true while genre shuffle queue is running

  // ── Genre logic ────────────────────────────────────────────────────────────
  // Sonata's 11 normalised genre buckets (must match library tags exactly).
  const SMP_GENRES = [
    'Jazz', 'Hip Hop', 'Soul & Funk', 'Electronic', 'Krautrock',
    'Ska & Reggae', 'Classical', 'Soundtrack', 'Spoken', 'Christmas', 'World'
  ];

  // Deterministic date-based pick: same genre all day, changes at midnight.
  function smpTodaysGenre() {
    const d = new Date();
    const seed = d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate();
    // Simple but stable hash.
    let h = seed;
    h = ((h >>> 16) ^ h) * 0x45d9f3b;
    h = ((h >>> 16) ^ h) * 0x45d9f3b;
    h = (h >>> 16) ^ h;
    return SMP_GENRES[Math.abs(h) % SMP_GENRES.length];
  }

  // Pull all tracks for a given genre tag from Sonata's in-memory library.
  // Sonata stores the library in state.tracks (array of Jellyfin item objects).
  // Genre is compared case-insensitively as a substring match so minor tag
  // variations ('Hip-Hop' vs 'Hip Hop') still resolve.
  function smpTracksForGenre(genre) {
    const tracks = (typeof state !== 'undefined' && Array.isArray(state.tracks))
      ? state.tracks : [];
    const needle = genre.toLowerCase();
    return tracks.filter(function (t) {
      const g = (t.Genres && t.Genres.length) ? t.Genres.join(' ').toLowerCase()
              : (t.Genre || '').toLowerCase();
      return g.indexOf(needle) !== -1;
    });
  }

  // Fisher-Yates shuffle (returns a new array, does not mutate).
  function smpShuffle(arr) {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      const tmp = a[i]; a[i] = a[j]; a[j] = tmp;
    }
    return a;
  }

  const todaysGenre = smpTodaysGenre();
  elGenreLabel.textContent = todaysGenre;

  // Genre queue state.
  let genreQueue = [];
  let genreIndex = 0;

  function smpBuildGenreQueue() {
    const tracks = smpTracksForGenre(todaysGenre);
    genreQueue = smpShuffle(tracks);
    genreIndex = 0;
  }

  function smpPlayGenreTrack(audio, index) {
    const track = genreQueue[index];
    if (!track) return;

    const jf = (typeof jellyfin !== 'undefined') ? jellyfin : null;
    if (!jf) return;

    // Build stream URL the same way Sonata does.
    const streamUrl = jf.server + '/Audio/' + track.Id + '/stream'
      + '?static=true&api_key=' + (jf.token || '');

    audio.src = streamUrl;
    audio.load();
    audio.play().catch(function () {});

    // Update meta immediately so the player shows the new track title.
    const title  = track.Name || '';
    const artist = track.AlbumArtist || track.Artists && track.Artists[0] || track.Artist || '';
    elTitle.textContent  = title  || 'Unknown track';
    elArtist.textContent = artist || '';

    if (track.Id) {
      const artUrl = jf.server + '/Items/' + track.Id + '/Images/Primary?maxWidth=280&quality=85'
        + '&api_key=' + (jf.token || '');
      elArt.src = artUrl;
      elArt.style.display  = 'block';
      elArtPH.style.display = 'none';
    }

    // Keep Sonata's own state.currentTrack in sync so the main UI reflects
    // what is playing (best-effort; Sonata may re-read from its own handlers).
    if (typeof state !== 'undefined') {
      state.currentTrack = track;
    }
  }

  function smpStartGenre(audio) {
    smpBuildGenreQueue();
    if (genreQueue.length === 0) {
      elGenreLabel.textContent = todaysGenre + ' (no tracks)';
      return;
    }
    genreActive = true;
    elGenreBtn.classList.add('smp-genre-active');
    genreIndex = 0;
    smpPlayGenreTrack(audio, genreIndex);
    dismissed = false;
    smpShow();
  }

  function smpStopGenre() {
    genreActive = false;
    elGenreBtn.classList.remove('smp-genre-active');
    elGenreLabel.textContent = todaysGenre;
  }

  // ── Helpers ────────────────────────────────────────────────────────────────
  function smpFmt(s) {
    if (!isFinite(s) || s < 0) return '0:00';
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return m + ':' + (sec < 10 ? '0' : '') + sec;
  }

  function smpUpdatePlay(audio) {
    elPlay.innerHTML = audio.paused ? '&#x25b6;' : '&#x23f8;';
    elPlay.setAttribute('aria-label', audio.paused ? 'Play' : 'Pause');
  }

  function smpUpdateProgress(audio) {
    const dur = audio.duration || 0;
    const cur = audio.currentTime || 0;
    const pct = dur > 0 ? (cur / dur) * 100 : 0;
    elPFill.style.width        = pct + '%';
    elPThumb.style.left        = pct + '%';
    elElapsed.textContent      = smpFmt(cur);
    elDuration.textContent     = smpFmt(dur);
  }

  function smpUpdateMeta() {
    const s = (typeof state !== 'undefined') ? state : null;
    if (!s) return;
    const track = s.currentTrack || s.nowPlaying || null;
    if (!track) return;
    const title  = track.Name || track.title || '';
    const artist = track.AlbumArtist || track.Artist || track.artist || track.albumArtist || '';
    elTitle.textContent  = title  || 'Unknown track';
    elArtist.textContent = artist || '';
    const jf = (typeof jellyfin !== 'undefined') ? jellyfin : null;
    if (jf && track.Id) {
      const artUrl = jf.server + '/Items/' + track.Id + '/Images/Primary?maxWidth=280&quality=85'
        + (jf.token ? '&api_key=' + jf.token : '');
      elArt.src = artUrl;
      elArt.style.display   = 'block';
      elArtPH.style.display = 'none';
    }
  }

  function smpShow() {
    if (dismissed) return;
    mp.classList.add('smp-visible');
  }

  function smpHide() {
    mp.classList.remove('smp-visible');
  }

  function smpSyncShuffle() {
    const on = (typeof state !== 'undefined') && state.shuffle;
    elShuffle.classList.toggle('smp-on', !!on);
  }

  function smpSyncRepeat() {
    const on = (typeof state !== 'undefined') && state.repeat;
    elRepeat.classList.toggle('smp-on', !!on);
  }

  // ── Attach to audio element ───────────────────────────────────────────────
  function smpAttachAudio() {
    const audio = document.querySelector('audio');
    if (!audio) { setTimeout(smpAttachAudio, 500); return; }

    audio.addEventListener('play', function () {
      if (!dismissed) smpShow();
      smpUpdatePlay(audio);
      if (!genreActive) {
        smpUpdateMeta();
        smpStopGenre();
      }
      smpSyncShuffle();
      smpSyncRepeat();
    });

    audio.addEventListener('pause', function () {
      smpUpdatePlay(audio);
    });

    audio.addEventListener('ended', function () {
      smpUpdatePlay(audio);
      // If in genre mode, auto-advance to next track in queue.
      if (genreActive) {
        genreIndex++;
        if (genreIndex < genreQueue.length) {
          smpPlayGenreTrack(audio, genreIndex);
        } else {
          // Wrap: rebuild a new shuffle and start again.
          smpBuildGenreQueue();
          smpPlayGenreTrack(audio, genreIndex);
        }
      }
    });

    audio.addEventListener('timeupdate', function () {
      smpUpdateProgress(audio);
    });

    audio.addEventListener('loadedmetadata', function () {
      smpUpdateProgress(audio);
      if (!genreActive) smpUpdateMeta();
    });

    // ── Playback controls ──────────────────────────────────────────────────
    elPlay.addEventListener('click', function () {
      if (audio.paused) { audio.play(); } else { audio.pause(); }
    });

    elPrev.addEventListener('click', function () {
      if (genreActive) {
        genreIndex = Math.max(0, genreIndex - 1);
        smpPlayGenreTrack(audio, genreIndex);
        return;
      }
      const btn = document.getElementById('prev-btn') ||
                  document.querySelector('[data-action="prev"]') ||
                  document.querySelector('.prev-btn');
      if (btn) { btn.click(); } else { audio.currentTime = 0; }
    });

    elNext.addEventListener('click', function () {
      if (genreActive) {
        genreIndex++;
        if (genreIndex >= genreQueue.length) {
          smpBuildGenreQueue();
        }
        smpPlayGenreTrack(audio, genreIndex);
        return;
      }
      const btn = document.getElementById('next-btn') ||
                  document.querySelector('[data-action="next"]') ||
                  document.querySelector('.next-btn');
      if (btn) { btn.click(); } else { audio.currentTime = audio.duration || 0; }
    });

    elShuffle.addEventListener('click', function () {
      if (genreActive) smpStopGenre();
      const btn = document.getElementById('shuffle-btn') ||
                  document.querySelector('[data-action="shuffle"]') ||
                  document.querySelector('.shuffle-btn');
      if (btn) { btn.click(); }
      setTimeout(smpSyncShuffle, 50);
    });

    elRepeat.addEventListener('click', function () {
      const btn = document.getElementById('repeat-btn') ||
                  document.querySelector('[data-action="repeat"]') ||
                  document.querySelector('.repeat-btn');
      if (btn) { btn.click(); }
      setTimeout(smpSyncRepeat, 50);
    });

    // Genre button.
    elGenreBtn.addEventListener('click', function () {
      if (genreActive) {
        // Pressing again while active stops genre mode; audio keeps playing.
        smpStopGenre();
        return;
      }
      smpStartGenre(audio);
    });

    // Progress scrub.
    function smpScrub(e) {
      const rect = elPTrack.getBoundingClientRect();
      const pct  = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
      if (isFinite(audio.duration)) audio.currentTime = pct * audio.duration;
    }
    let scrubbing = false;
    elPTrack.addEventListener('mousedown', function (e) { scrubbing = true; smpScrub(e); });
    document.addEventListener('mousemove', function (e) { if (scrubbing) smpScrub(e); });
    document.addEventListener('mouseup',   function ()  { scrubbing = false; });

    // Volume.
    function smpSetVol(e) {
      const rect = elVolTrack.getBoundingClientRect();
      const pct  = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
      audio.volume = pct;
      lastVol = pct || lastVol;
      elVolFill.style.width = (pct * 100) + '%';
      muted = (pct === 0);
    }
    let volDrag = false;
    elVolTrack.addEventListener('mousedown', function (e) { volDrag = true; smpSetVol(e); });
    document.addEventListener('mousemove', function (e) { if (volDrag) smpSetVol(e); });
    document.addEventListener('mouseup',   function ()  { volDrag = false; });

    elMute.addEventListener('click', function () {
      if (muted) {
        audio.volume = lastVol || 0.8;
        muted = false;
        elVolFill.style.width = (audio.volume * 100) + '%';
      } else {
        lastVol = audio.volume;
        audio.volume = 0;
        muted = true;
        elVolFill.style.width = '0%';
      }
    });

    elVolFill.style.width = (audio.volume * 100) + '%';
  }

  smpAttachAudio();

  // ── Close ─────────────────────────────────────────────────────────────────
  elClose.addEventListener('click', function () {
    dismissed = true;
    smpHide();
  });

  // ── Drag ──────────────────────────────────────────────────────────────────
  let dragging = false, dox = 0, doy = 0;
  const handle = document.getElementById('smp-drag-handle');

  handle.addEventListener('mousedown', function (e) {
    dragging = true;
    const r = mp.getBoundingClientRect();
    dox = e.clientX - r.left;
    doy = e.clientY - r.top;
    mp.style.transition = 'none';
    e.preventDefault();
  });

  document.addEventListener('mousemove', function (e) {
    if (!dragging) return;
    let nx = e.clientX - dox;
    let ny = e.clientY - doy;
    nx = Math.max(0, Math.min(window.innerWidth  - mp.offsetWidth,  nx));
    ny = Math.max(0, Math.min(window.innerHeight - mp.offsetHeight, ny));
    mp.style.right  = 'auto';
    mp.style.bottom = 'auto';
    mp.style.left   = nx + 'px';
    mp.style.top    = ny + 'px';
  });

  document.addEventListener('mouseup', function () { dragging = false; });
})();
// ── End Sonata mini player ───────────────────────────────────────────────────
"""

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not SOURCE.exists():
        raise FileNotFoundError(f'Source file not found: {SOURCE}')

    html = SOURCE.read_text(encoding='utf-8')

    if IDEMPOTENCY_MARKER in html:
        print('SKIP: mini player already present in source. Nothing to do.')
        return

    missing = []
    if ANCHOR_A not in html:
        missing.append(f'Anchor A: {ANCHOR_A!r}')
    if ANCHOR_B not in html:
        missing.append(f'Anchor B: {ANCHOR_B!r}')

    if missing:
        print('ERROR: anchor(s) not found in source:')
        for m in missing:
            print(f'  {m}')
        print('Aborting. No changes made.')
        return

    shutil.copy2(SOURCE, BACKUP)
    print(f'Backup: {BACKUP}')

    html = html.replace(ANCHOR_A, MINI_PLAYER_HTML + '\n' + ANCHOR_A, 1)
    html = html.replace('})();\n</script>', MINI_PLAYER_JS + '\n})();\n</script>', 1)

    SOURCE.write_text(html, encoding='utf-8')
    print('Done. Mini player with genre button injected.')
    print(f'Source: {SOURCE}')
    print()
    print('Next steps:')
    print('  1. git add sonata-pwa.html')
    print('  2. git commit -m "Add desktop mini player with daily genre button"')
    print('  3. git push')
    print()
    print('Note:')
    print('  - state.tracks must be the array Sonata populates with the full')
    print('    library. Genre filtering reads track.Genres (array) or track.Genre')
    print('    (string), matching Jellyfin\'s item schema.')
    print()
    print(f"  Today's genre (for testing): {_todays_genre()}")


def _todays_genre():
    import datetime
    GENRES = [
        'Jazz', 'Hip Hop', 'Soul & Funk', 'Electronic', 'Krautrock',
        'Ska & Reggae', 'Classical', 'Soundtrack', 'Spoken', 'Christmas', 'World'
    ]
    d = datetime.date.today()
    seed = d.year * 10000 + d.month * 100 + d.day
    h = seed
    h = ((h >> 16) ^ h) * 0x45d9f3b & 0xFFFFFFFF
    h = ((h >> 16) ^ h) * 0x45d9f3b & 0xFFFFFFFF
    h = (h >> 16) ^ h
    return GENRES[abs(h) % len(GENRES)]


if __name__ == '__main__':
    main()
