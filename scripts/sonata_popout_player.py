# sonata_popout_player.py
# ============================================================
# Adds a pop-out button to the desktop player bar (#vol-area).
# Clicking it opens a slim, self-contained popup window showing
# track title, artist, prev/play/next/shuffle/repeat controls,
# a progress bar with scrubbing, volume, and the daily genre
# button. The popup is independent of the main Sonata tab and
# survives switching to other tabs or windows.
#
# The popup is a self-contained HTML document written as a
# data: URL (no extra files needed). It polls the opener via
# window.opener for state and audio sync.
#
# Two anchors patched:
#   A. A new pop-out button injected into #vol-area HTML.
#   B. Pop-out JS injected before })();\n</script>.
#
# Safe by design:
#   - Bails loudly if either anchor is missing or not unique.
#   - Creates a timestamped backup before writing.
#   - Idempotent: refuses to run if already patched.
#
# Usage (from repo root):
#   python scripts\sonata_popout_player.py
# ============================================================

import shutil
from datetime import datetime
from pathlib import Path

SOURCE = Path('sonata-pwa.html')
BACKUP_SUFFIX = datetime.now().strftime('%Y%m%d-%H%M%S')
BACKUP = SOURCE.with_name(f'sonata-pwa.backup-{BACKUP_SUFFIX}.html')

IDEMPOTENCY_MARKER = 'id="popout-btn"'
ANCHOR_A = '</div>\n\n<!-- ═══════ MINI PLAYER (mobile) ═══════ -->'
ANCHOR_B = '})();\n</script>'

# ---------------------------------------------------------------------------
# A: Pop-out button injected into the player bar, just before </div> that
#    closes #player (which is immediately before the mobile mini player comment)
# ---------------------------------------------------------------------------

POPOUT_BUTTON_HTML = """  <button id="popout-btn" title="Pop out player" aria-label="Pop out player">
    <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
  </button>
"""

POPOUT_BUTTON_CSS = """
/* ── Pop-out button (injected by sonata_popout_player.py) ── */
#popout-btn {
  background: none;
  border: none;
  color: var(--text3);
  cursor: pointer;
  padding: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-left: 4px;
  border-radius: 6px;
  transition: color 0.12s, background 0.12s;
}
#popout-btn:hover { color: var(--text); background: var(--surface2); }
#popout-btn.popout-open { color: var(--accent); }
/* ── End pop-out button ── */
"""

# ---------------------------------------------------------------------------
# B: Pop-out JS
# ---------------------------------------------------------------------------

POPOUT_JS = r"""
// ── Sonata pop-out player (injected by sonata_popout_player.py) ─────────────
(function () {
  // Desktop only.
  if (typeof isMobile === 'function' && isMobile()) return;

  const btn = document.getElementById('popout-btn');
  if (!btn) return;

  // Inject CSS into the page's <head>.
  const style = document.createElement('style');
  style.textContent = `POPOUT_CSS_PLACEHOLDER`;
  document.head.appendChild(style);

  // ── Genre helpers (same hash as mini player) ──────────────────────────────
  const SOP_GENRES = [
    'Jazz', 'Hip Hop', 'Soul & Funk', 'Electronic', 'Krautrock',
    'Ska & Reggae', 'Classical', 'Soundtrack', 'Spoken', 'Christmas', 'World'
  ];

  function sopTodaysGenre() {
    const d = new Date();
    const seed = d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate();
    let h = seed;
    h = ((h >>> 16) ^ h) * 0x45d9f3b & 0xFFFFFFFF;
    h = ((h >>> 16) ^ h) * 0x45d9f3b & 0xFFFFFFFF;
    h = (h >>> 16) ^ h;
    return SOP_GENRES[Math.abs(h) % SOP_GENRES.length];
  }

  function sopTracksForGenre(genre) {
    const tracks = (typeof state !== 'undefined' && Array.isArray(state.tracks))
      ? state.tracks : [];
    const needle = genre.toLowerCase();
    return tracks.filter(function (t) {
      const g = (t.Genres && t.Genres.length) ? t.Genres.join(' ').toLowerCase()
              : (t.Genre || t.genre || '').toLowerCase();
      return g.indexOf(needle) !== -1;
    });
  }

  function sopShuffle(arr) {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      const tmp = a[i]; a[i] = a[j]; a[j] = tmp;
    }
    return a;
  }

  const todaysGenre = sopTodaysGenre();

  // Genre queue (lives in the opener, managed here).
  let genreQueue  = [];
  let genreIndex  = 0;
  let genreActive = false;

  function sopBuildGenreQueue() {
    genreQueue = sopShuffle(sopTracksForGenre(todaysGenre));
    genreIndex = 0;
  }

  function sopPlayGenreTrack(audio, index) {
    const track = genreQueue[index];
    if (!track) return;
    const jf = (typeof jellyfin !== 'undefined') ? jellyfin : null;
    if (!jf) return;
    audio.src = jf.server + '/Audio/' + track.Id + '/stream?static=true&api_key=' + (jf.token || '');
    audio.load();
    audio.play().catch(function () {});
    if (typeof state !== 'undefined') state.currentTrack = track;
  }

  // ── The popup HTML document ───────────────────────────────────────────────
  // Written as a Blob URL so no extra file is needed.
  const POPUP_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Sonata</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg:      #1c1c1e;
    --bg2:     #2c2c2e;
    --border:  rgba(255,255,255,0.09);
    --text:    #f2f2f7;
    --text2:   rgba(242,242,247,0.55);
    --accent:  #c8a96e;
    --radius:  0px;
  }
  html, body {
    width: 100%; height: 100%;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    overflow: hidden;
    user-select: none;
  }
  #wrap {
    display: flex;
    flex-direction: column;
    height: 100%;
    padding: 12px 14px 10px;
    gap: 10px;
  }
  #meta {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  #pop-title {
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text);
  }
  #pop-artist {
    font-size: 11px;
    color: var(--text2);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  #pop-progress-row {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .pop-time {
    font-size: 9px;
    color: var(--text2);
    min-width: 24px;
    font-variant-numeric: tabular-nums;
    opacity: 0.6;
  }
  .pop-time.r { text-align: right; }
  #pop-prog-track {
    flex: 1;
    height: 3px;
    background: rgba(255,255,255,0.1);
    border-radius: 2px;
    position: relative;
    cursor: pointer;
  }
  #pop-prog-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 2px;
    pointer-events: none;
    width: 0%;
  }
  #pop-prog-thumb {
    position: absolute;
    top: 50%; left: 0%;
    width: 9px; height: 9px;
    background: var(--text);
    border-radius: 50%;
    transform: translate(-50%, -50%);
    pointer-events: none;
    box-shadow: 0 0 0 2px rgba(200,169,110,0.3);
  }
  #pop-btn-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 2px;
  }
  .pop-ctrl {
    background: none; border: none;
    cursor: pointer;
    color: rgba(255,255,255,0.45);
    padding: 4px;
    display: flex; align-items: center; justify-content: center;
    border-radius: 5px;
    font-size: 14px;
    transition: color 0.12s;
  }
  .pop-ctrl:hover { color: rgba(255,255,255,0.9); }
  .pop-ctrl.on { color: var(--accent); }
  #pop-play {
    width: 34px; height: 34px;
    background: var(--text);
    border: none; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer;
    color: var(--bg);
    font-size: 13px;
    transition: transform 0.1s, background 0.12s;
  }
  #pop-play:hover { background: #fff; transform: scale(1.06); }
  #pop-play:active { transform: scale(0.95); }
  #pop-vol-row {
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 0 2px;
  }
  .pop-vol-icon {
    font-size: 12px;
    color: rgba(255,255,255,0.28);
    cursor: pointer;
    transition: color 0.12s;
  }
  .pop-vol-icon:hover { color: rgba(255,255,255,0.7); }
  #pop-vol-track {
    flex: 1; height: 2px;
    background: rgba(255,255,255,0.1);
    border-radius: 2px;
    cursor: pointer;
  }
  #pop-vol-fill {
    height: 100%;
    background: rgba(255,255,255,0.28);
    border-radius: 2px;
    pointer-events: none;
  }
  #pop-genre-row {
    padding: 0 2px;
  }
  #pop-genre-btn {
    width: 100%;
    background: rgba(255,255,255,0.05);
    border: 0.5px solid rgba(255,255,255,0.11);
    border-radius: 20px;
    color: rgba(255,255,255,0.45);
    font-size: 10px;
    font-family: inherit;
    padding: 5px 10px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    transition: background 0.15s, color 0.15s, border-color 0.15s;
  }
  #pop-genre-btn:hover {
    background: rgba(255,255,255,0.09);
    color: rgba(255,255,255,0.8);
  }
  #pop-genre-btn.on {
    background: rgba(200,169,110,0.14);
    border-color: rgba(200,169,110,0.38);
    color: var(--accent);
  }
  #pop-genre-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  #titlebar {
    position: fixed; top: 0; left: 0; right: 0;
    height: 28px;
    -webkit-app-region: drag;
    background: var(--bg);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    padding: 0 10px;
    gap: 6px;
    font-size: 10px;
    color: var(--text2);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  #titlebar svg { opacity: 0.4; }
  body { padding-top: 28px; }
  #wrap { height: calc(100% - 28px); }
</style>
</head>
<body>
<div id="titlebar">
  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
  Sonata
</div>
<div id="wrap">
  <div id="meta">
    <div id="pop-title">Nothing playing</div>
    <div id="pop-artist"></div>
  </div>
  <div id="pop-progress-row">
    <span class="pop-time" id="pop-elapsed">0:00</span>
    <div id="pop-prog-track">
      <div id="pop-prog-fill"></div>
      <div id="pop-prog-thumb"></div>
    </div>
    <span class="pop-time r" id="pop-duration">0:00</span>
  </div>
  <div id="pop-btn-row">
    <button class="pop-ctrl" id="pop-shuf" title="Shuffle">&#x21c4;</button>
    <button class="pop-ctrl" id="pop-prev" title="Previous">&#x23ee;</button>
    <button id="pop-play" aria-label="Play/pause">&#x25b6;</button>
    <button class="pop-ctrl" id="pop-next" title="Next">&#x23ed;</button>
    <button class="pop-ctrl" id="pop-rep" title="Repeat">&#x1f501;</button>
  </div>
  <div id="pop-vol-row">
    <span class="pop-vol-icon" id="pop-mute">&#x1f507;</span>
    <div id="pop-vol-track"><div id="pop-vol-fill" style="width:80%"></div></div>
    <span class="pop-vol-icon">&#x1f50a;</span>
  </div>
  <div id="pop-genre-row">
    <button id="pop-genre-btn">
      <span>&#x266b;</span>
      <span id="pop-genre-label">Today\u2019s genre</span>
    </button>
  </div>
</div>
<script>
(function () {
  const op = window.opener;
  if (!op) { document.getElementById('pop-title').textContent = 'No connection'; return; }

  function fmt(s) {
    if (!isFinite(s) || s < 0) return '0:00';
    const m = Math.floor(s / 60), sec = Math.floor(s % 60);
    return m + ':' + (sec < 10 ? '0' : '') + sec;
  }

  // Elements
  const elTitle    = document.getElementById('pop-title');
  const elArtist   = document.getElementById('pop-artist');
  const elElapsed  = document.getElementById('pop-elapsed');
  const elDuration = document.getElementById('pop-duration');
  const elPFill    = document.getElementById('pop-prog-fill');
  const elPThumb   = document.getElementById('pop-prog-thumb');
  const elPTrack   = document.getElementById('pop-prog-track');
  const elPlay     = document.getElementById('pop-play');
  const elPrev     = document.getElementById('pop-prev');
  const elNext     = document.getElementById('pop-next');
  const elShuf     = document.getElementById('pop-shuf');
  const elRep      = document.getElementById('pop-rep');
  const elVolTrack = document.getElementById('pop-vol-track');
  const elVolFill  = document.getElementById('pop-vol-fill');
  const elMute     = document.getElementById('pop-mute');
  const elGenreBtn = document.getElementById('pop-genre-btn');
  const elGenreLabel = document.getElementById('pop-genre-label');

  let muted = false, lastVol = 0.8;

  // ── Poll opener for state ─────────────────────────────────────────────────
  // Genre label is sent from opener via postMessage on open.
  window.addEventListener('message', function (e) {
    if (e.data && e.data.type === 'sop-init') {
      elGenreLabel.textContent = e.data.genre || 'Today\u2019s genre';
      elVolFill.style.width = ((e.data.volume || 0.8) * 100) + '%';
    }
    if (e.data && e.data.type === 'sop-genre-state') {
      elGenreBtn.classList.toggle('on', !!e.data.active);
    }
  });

  // Poll audio state from opener every 250ms.
  setInterval(function () {
    try {
      const audio = op.document.querySelector('audio');
      if (!audio) return;
      const paused = audio.paused;
      elPlay.innerHTML = paused ? '&#x25b6;' : '&#x23f8;';
      const dur = audio.duration || 0;
      const cur = audio.currentTime || 0;
      const pct = dur > 0 ? (cur / dur) * 100 : 0;
      elPFill.style.width  = pct + '%';
      elPThumb.style.left  = pct + '%';
      elElapsed.textContent  = fmt(cur);
      elDuration.textContent = fmt(dur);
      elVolFill.style.width  = (audio.volume * 100) + '%';
      const s = op.state;
      if (s) {
        elShuf.classList.toggle('on', !!s.shuffle);
        elRep.classList.toggle('on',  !!s.repeat);
        const t = s.currentTrack || s.nowPlaying;
        if (t) {
          elTitle.textContent  = t.Name  || t.title  || 'Unknown';
          elArtist.textContent = t.AlbumArtist || t.Artist || t.artist || '';
        }
      }
    } catch(e) { /* opener navigated away */ }
  }, 250);

  // ── Controls: delegate to opener ─────────────────────────────────────────
  elPlay.addEventListener('click', function () {
    try {
      const audio = op.document.querySelector('audio');
      if (audio.paused) audio.play(); else audio.pause();
    } catch(e) {}
  });

  elPrev.addEventListener('click', function () {
    try { op.postMessage({ type: 'sop-cmd', cmd: 'prev' }, '*'); } catch(e) {}
  });

  elNext.addEventListener('click', function () {
    try { op.postMessage({ type: 'sop-cmd', cmd: 'next' }, '*'); } catch(e) {}
  });

  elShuf.addEventListener('click', function () {
    try { op.postMessage({ type: 'sop-cmd', cmd: 'shuffle' }, '*'); } catch(e) {}
  });

  elRep.addEventListener('click', function () {
    try { op.postMessage({ type: 'sop-cmd', cmd: 'repeat' }, '*'); } catch(e) {}
  });

  elGenreBtn.addEventListener('click', function () {
    try { op.postMessage({ type: 'sop-cmd', cmd: 'genre' }, '*'); } catch(e) {}
  });

  // Progress scrub
  function scrub(e) {
    try {
      const audio = op.document.querySelector('audio');
      const rect = elPTrack.getBoundingClientRect();
      const pct  = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
      if (isFinite(audio.duration)) audio.currentTime = pct * audio.duration;
    } catch(e) {}
  }
  let scrubbing = false;
  elPTrack.addEventListener('mousedown', function (e) { scrubbing = true; scrub(e); });
  document.addEventListener('mousemove', function (e) { if (scrubbing) scrub(e); });
  document.addEventListener('mouseup',   function ()  { scrubbing = false; });

  // Volume
  function setVol(e) {
    try {
      const audio = op.document.querySelector('audio');
      const rect  = elVolTrack.getBoundingClientRect();
      const pct   = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
      audio.volume = pct;
      lastVol = pct || lastVol;
      muted = (pct === 0);
    } catch(e) {}
  }
  let volDrag = false;
  elVolTrack.addEventListener('mousedown', function (e) { volDrag = true; setVol(e); });
  document.addEventListener('mousemove', function (e) { if (volDrag) setVol(e); });
  document.addEventListener('mouseup',   function ()  { volDrag = false; });

  elMute.addEventListener('click', function () {
    try {
      const audio = op.document.querySelector('audio');
      if (muted) { audio.volume = lastVol || 0.8; muted = false; }
      else       { lastVol = audio.volume; audio.volume = 0; muted = true; }
    } catch(e) {}
  });

  // Notify opener when closed so it can update button state.
  window.addEventListener('beforeunload', function () {
    try { op.postMessage({ type: 'sop-closed' }, '*'); } catch(e) {}
  });
})();
<\/script>
</body>
</html>`;

  // ── Opener-side command handler ───────────────────────────────────────────
  window.addEventListener('message', function (e) {
    if (!e.data || e.data.type !== 'sop-cmd') return;
    const cmd = e.data.cmd;
    const audio = document.querySelector('audio');

    if (cmd === 'prev') {
      const b = document.getElementById('prev-btn'); if (b) b.click();
    } else if (cmd === 'next') {
      if (genreActive) {
        genreIndex++;
        if (genreIndex >= genreQueue.length) sopBuildGenreQueue();
        sopPlayGenreTrack(audio, genreIndex);
      } else {
        const b = document.getElementById('next-btn'); if (b) b.click();
      }
    } else if (cmd === 'shuffle') {
      if (genreActive) sopStopGenre();
      const b = document.getElementById('shuffle-btn'); if (b) b.click();
    } else if (cmd === 'repeat') {
      const b = document.getElementById('repeat-btn'); if (b) b.click();
    } else if (cmd === 'genre') {
      if (genreActive) {
        sopStopGenre();
      } else {
        sopStartGenre(audio);
      }
    }
  });

  window.addEventListener('message', function (e) {
    if (e.data && e.data.type === 'sop-closed') {
      btn.classList.remove('popout-open');
      popupWin = null;
    }
  });

  // ── Genre actions (run in opener) ─────────────────────────────────────────
  function sopStopGenre() {
    genreActive = false;
    if (popupWin && !popupWin.closed) {
      popupWin.postMessage({ type: 'sop-genre-state', active: false }, '*');
    }
  }

  function sopStartGenre(audio) {
    sopBuildGenreQueue();
    if (genreQueue.length === 0) return;
    genreActive = true;
    genreIndex  = 0;
    sopPlayGenreTrack(audio, genreIndex);
    if (popupWin && !popupWin.closed) {
      popupWin.postMessage({ type: 'sop-genre-state', active: true }, '*');
    }
  }

  // Auto-advance genre queue on track end.
  function sopAttachGenreAdvance() {
    const audio = document.querySelector('audio');
    if (!audio) { setTimeout(sopAttachGenreAdvance, 500); return; }
    audio.addEventListener('ended', function () {
      if (!genreActive) return;
      genreIndex++;
      if (genreIndex >= genreQueue.length) sopBuildGenreQueue();
      sopPlayGenreTrack(audio, genreIndex);
    });
    // Stop genre mode if the main UI starts a new track.
    audio.addEventListener('play', function () {
      // If the src changed but we didn't trigger it, cancel genre mode.
      if (genreActive && genreQueue.length > 0) {
        const jf = (typeof jellyfin !== 'undefined') ? jellyfin : null;
        if (jf) {
          const expected = jf.server + '/Audio/' + genreQueue[genreIndex].Id + '/stream';
          if (audio.src && !audio.src.startsWith(expected)) {
            sopStopGenre();
          }
        }
      }
    });
  }
  sopAttachGenreAdvance();

  // ── Pop-out window management ─────────────────────────────────────────────
  let popupWin = null;
  const POPUP_W = 300;
  const POPUP_H = 230;

  btn.addEventListener('click', function () {
    if (popupWin && !popupWin.closed) {
      popupWin.focus();
      return;
    }

    const left = window.screen.width  - POPUP_W - 24;
    const top  = window.screen.height - POPUP_H - 60;

    const blob = new Blob([POPUP_HTML], { type: 'text/html' });
    const url  = URL.createObjectURL(blob);

    popupWin = window.open(
      url,
      'SonataPopout',
      'width=' + POPUP_W + ',height=' + POPUP_H +
      ',left=' + left + ',top=' + top +
      ',resizable=yes,scrollbars=no,toolbar=no,menubar=no,location=no,status=no'
    );

    if (!popupWin) {
      alert('Pop-up blocked. Please allow pop-ups for this site in your browser settings.');
      return;
    }

    btn.classList.add('popout-open');

    // Send init data once the popup has loaded.
    popupWin.addEventListener('load', function () {
      const audio = document.querySelector('audio');
      popupWin.postMessage({
        type:   'sop-init',
        genre:  todaysGenre,
        volume: audio ? audio.volume : 0.8
      }, '*');
      popupWin.postMessage({ type: 'sop-genre-state', active: genreActive }, '*');
      URL.revokeObjectURL(url);
    });

    popupWin.addEventListener('beforeunload', function () {
      btn.classList.remove('popout-open');
      popupWin = null;
    });
  });
})();
// ── End Sonata pop-out player ────────────────────────────────────────────────
"""

# The CSS is embedded inside the JS string as a placeholder — replace it now.
# This avoids any quoting issues with backticks inside the template literal.
POPOUT_BUTTON_CSS_ESCAPED = POPOUT_BUTTON_CSS.replace('`', r'\`').replace('${', r'\${')
POPOUT_JS_FINAL = POPOUT_JS.replace('`POPOUT_CSS_PLACEHOLDER`',
                                     '`' + POPOUT_BUTTON_CSS_ESCAPED + '`')

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not SOURCE.exists():
        raise FileNotFoundError(f'Source file not found: {SOURCE}')

    html = SOURCE.read_text(encoding='utf-8')

    if IDEMPOTENCY_MARKER in html:
        print('SKIP: pop-out player already present. Nothing to do.')
        return

    # Check anchors exist and are unique.
    missing = []
    for label, anchor in [('A', ANCHOR_A), ('B', ANCHOR_B)]:
        count = html.count(anchor)
        if count == 0:
            missing.append(f'Anchor {label} not found: {anchor!r}')
        elif count > 1:
            missing.append(f'Anchor {label} not unique ({count} matches): {anchor!r}')

    if missing:
        print('ERROR:')
        for m in missing:
            print(f'  {m}')
        print('Aborting. No changes made.')
        return

    shutil.copy2(SOURCE, BACKUP)
    print(f'Backup: {BACKUP}')

    # Patch A: inject pop-out button into player bar just before </div> that
    # closes #player (identified by the mobile mini player comment that follows).
    html = html.replace(ANCHOR_A, POPOUT_BUTTON_HTML + ANCHOR_A, 1)

    # Patch B: inject JS before the closing })(); of the main script block.
    html = html.replace('})();\n</script>', POPOUT_JS_FINAL + '\n})();\n</script>', 1)

    SOURCE.write_text(html, encoding='utf-8')
    print('Done. Pop-out player injected.')
    print(f'Source: {SOURCE}')
    print()
    print('Next steps:')
    print('  1. git add sonata-pwa.html scripts\\sonata_popout_player.py')
    print('  2. git commit -m "Add pop-out mini player window"')
    print('  3. git push')
    print()
    print('Browser note: pop-ups must be allowed for the Sonata site.')
    print('Chrome: click the blocked-popup icon in the address bar once,')
    print('then choose "Always allow pop-ups from this site".')


if __name__ == '__main__':
    main()
