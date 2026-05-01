#!/usr/bin/env python3
"""
Sonata PWA - April 2026 tweaks, Round 1 of 4
=============================================

Applies four small, well-scoped changes to your existing sonata-pwa.html:

  1. Home album cards navigate only (no auto-play)
  3. Artist names tappable as links across album views
  6. All Tracks view removed from navigation
  8. Home -> drill -> back returns to home (not the album list)

USAGE
-----
Put this script next to your sonata-pwa.html and run:

    python sonata_round1.py

Default behaviour:
  - Reads:  sonata-pwa.html
  - Writes: sonata-pwa.html (in place)
  - Backs up the original to: sonata-pwa.backup-round1.html

Pass a different filename if your file is named something else:

    python sonata_round1.py my-sonata.html

The script is strict: every patch has a unique anchor in the file. If an
anchor isn't found exactly once, it stops and tells you which patch failed
without modifying anything.
"""
from __future__ import annotations
import sys
import shutil
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def must_replace(html: str, old: str, new: str, label: str) -> str:
    """Replace `old` with `new` exactly once. Bail loudly otherwise."""
    count = html.count(old)
    if count == 0:
        raise SystemExit(
            f"FAIL [{label}]: anchor not found in source file.\n"
            f"  Expected substring (first 160 chars):\n  {old[:160]!r}"
        )
    if count > 1:
        raise SystemExit(
            f"FAIL [{label}]: anchor found {count} times, must be unique.\n"
            f"  Substring (first 160 chars):\n  {old[:160]!r}"
        )
    return html.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Tweak 6 - remove the All Tracks view from sidebar navigation
# ---------------------------------------------------------------------------

def tweak6_remove_all_tracks(html: str) -> str:
    # Sidebar item for All Tracks - drop the whole div block.
    html = must_replace(
        html,
        '''<div class="nav-item" data-view="all">
        <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
        All Tracks
      </div>
      ''',
        '',
        'tweak6.sidebar-nav',
    )

    # Redirect any 'all' navigation to home so legacy callers (search-clear,
    # back buttons, deep state) land somewhere sensible. The renderView
    # dispatch had a case for 'all' that called renderTrackList(getVisibleTracks);
    # rewrite it to fall through to home.
    html = must_replace(
        html,
        "  if (v === 'home')         { renderHomeView();             return; }\n"
        "  if (v === 'all')          { renderTrackList(getVisibleTracks()); return; }\n",
        "  if (v === 'home' || v === 'all') { renderHomeView();      return; }\n",
        'tweak6.renderView-dispatch',
    )

    # The mobile playlist back button used to land on 'all'. Send it home instead.
    html = must_replace(
        html,
        "    if (isMobile()) { state.currentView = 'playlists-mobile'; state.drillTarget = null; renderView(); }\n"
        "    else { state.currentView = 'all'; state.drillTarget = null; renderView(); }\n",
        "    if (isMobile()) { state.currentView = 'playlists-mobile'; state.drillTarget = null; renderView(); }\n"
        "    else { state.currentView = 'home'; state.drillTarget = null; renderView(); }\n",
        'tweak6.playlist-back',
    )

    # bnavMap had 'all' -> 'all'. Map it to home so any stale references behave.
    html = must_replace(
        html,
        "    'home': 'home',\n"
        "    'all': 'all', 'search': 'all',\n",
        "    'home': 'home',\n"
        "    'search': 'home',\n",
        'tweak6.bnavMap',
    )

    # Search input on desktop: clearing the box used to set view 'all'. Send home.
    html = must_replace(
        html,
        "  state.currentView = state.searchQ ? 'search' : 'all';\n"
        "  state.drillTarget = null;\n"
        "  renderView();\n"
        "};\n\n"
        "// Search (mobile)",
        "  state.currentView = state.searchQ ? 'search' : 'home';\n"
        "  state.drillTarget = null;\n"
        "  renderView();\n"
        "};\n\n"
        "// Search (mobile)",
        'tweak6.search-desktop',
    )

    # Same for the mobile search input.
    html = must_replace(
        html,
        "  state.currentView = state.searchQ ? 'search' : 'all';\n"
        "  state.drillTarget = null;\n"
        "  renderView();\n"
        "};\n\n"
        "// ══════════════════════════════════════════════\n"
        "//  RENDER",
        "  state.currentView = state.searchQ ? 'search' : 'home';\n"
        "  state.drillTarget = null;\n"
        "  renderView();\n"
        "};\n\n"
        "// ══════════════════════════════════════════════\n"
        "//  RENDER",
        'tweak6.search-mobile',
    )

    # Mobile search toggle close handler also resets view to 'all'.
    html = must_replace(
        html,
        "    state.searchQ = '';\n"
        "    state.currentView = 'all';\n"
        "    document.getElementById('mob-search').value = '';",
        "    state.searchQ = '';\n"
        "    state.currentView = 'home';\n"
        "    document.getElementById('mob-search').value = '';",
        'tweak6.mobile-search-toggle',
    )

    # If the search "Artists" tile is clicked while searching, the existing
    # code redirects to 'artists' and clears the box. Untouched - that path
    # still works.

    # The empty state's setView fallback used 'all' too.
    html = must_replace(
        html,
        "    document.getElementById('empty-load-btn').onclick = isConfigured ? triggerRefresh : openSettings;\n"
        "    return;\n"
        "  }\n"
        "\n"
        "  const v = state.currentView;",
        "    document.getElementById('empty-load-btn').onclick = isConfigured ? triggerRefresh : openSettings;\n"
        "    return;\n"
        "  }\n"
        "\n"
        "  // Tweak 6: 'all' view removed - legacy state values land on home.\n"
        "  if (state.currentView === 'all') state.currentView = 'home';\n"
        "  const v = state.currentView;",
        'tweak6.renderView-coerce',
    )

    # Playlist sidebar's setView('all') after deleting active playlist.
    html = must_replace(
        html,
        "      if (state.drillTarget?.value === btn.dataset.id) setView('all');\n",
        "      if (state.drillTarget?.value === btn.dataset.id) setView('home');\n",
        'tweak6.playlist-delete-redirect',
    )

    return html


# ---------------------------------------------------------------------------
# Tweak 8 - track drill origin so back from home returns to home
# ---------------------------------------------------------------------------

def tweak8_back_to_home(html: str) -> str:
    # Add a drillOrigin field to state so we know where a drill started.
    html = must_replace(
        html,
        "  drillTarget: null,\n"
        "  playlists: [],",
        "  drillTarget: null,\n"
        "  drillOrigin: null,   // 'home' when the user drilled in from the home screen\n"
        "  playlists: [],",
        'tweak8.state-field',
    )

    # When the user clicks an album card on the home screen, mark the origin
    # before drilling. Same go for the wheel of fortune.
    #
    # The home card click handler currently does:
    #   state.currentView = type === 'compilation' ? 'compilations' : (...);
    #   state.drillTarget = { type: ..., value: album };
    #   renderView();
    # We add a drillOrigin = 'home' just before drillTarget is set.
    html = must_replace(
        html,
        "      if (tracks.length) playTracksAt(tracks, 0);\n"
        "      state.currentView = type === 'compilation' ? 'compilations' : (type === 'djmix' ? 'djmixes' : 'albums');\n"
        "      state.drillTarget = { type: type === 'compilation' ? 'compilation' : (type === 'djmix' ? 'djmix' : 'album'), value: album };\n"
        "      renderView();\n",
        # Tweak 1 happens at the same anchor: drop the playTracksAt line.
        # Tweak 8 adds the drillOrigin marker.
        "      // Tweak 1: home album cards navigate only - don't auto-play.\n"
        "      // Tweak 8: mark the drill so back returns to home.\n"
        "      state.drillOrigin = 'home';\n"
        "      state.currentView = type === 'compilation' ? 'compilations' : (type === 'djmix' ? 'djmixes' : 'albums');\n"
        "      state.drillTarget = { type: type === 'compilation' ? 'compilation' : (type === 'djmix' ? 'djmix' : 'album'), value: album };\n"
        "      renderView();\n",
        'tweak1+8.home-card-click',
    )

    # Wheel of Fortune drills in too - mark its origin as home as well.
    html = must_replace(
        html,
        "  state.currentView = isCompilation ? 'compilations' : (isDjmix ? 'djmixes' : 'albums');\n"
        "  state.drillTarget = {\n"
        "    type:  isCompilation ? 'compilation' : (isDjmix ? 'djmix' : 'album'),\n"
        "    value: album,\n"
        "  };\n",
        "  state.drillOrigin = 'home';   // Tweak 8\n"
        "  state.currentView = isCompilation ? 'compilations' : (isDjmix ? 'djmixes' : 'albums');\n"
        "  state.drillTarget = {\n"
        "    type:  isCompilation ? 'compilation' : (isDjmix ? 'djmix' : 'album'),\n"
        "    value: album,\n"
        "  };\n",
        'tweak8.wheel-of-fortune',
    )

    # Any time the user navigates to a top-level view via setView (sidebar,
    # bottom nav), clear the drill origin - we are no longer in a drilled
    # state.
    html = must_replace(
        html,
        "function setView(view) {\n"
        "  state.currentView = view;\n"
        "  state.drillTarget = null;\n"
        "  state.searchQ = '';\n",
        "function setView(view) {\n"
        "  state.currentView = view;\n"
        "  state.drillTarget = null;\n"
        "  state.drillOrigin = null;   // Tweak 8: reset on top-level nav\n"
        "  state.searchQ = '';\n",
        'tweak8.setView-reset',
    )

    # The back button inside renderTrackList currently clears drillTarget and
    # re-renders the current top-level view. We override that when the drill
    # came from home, so back lands on home instead of the (e.g.) Albums grid.
    html = must_replace(
        html,
        "  if (document.getElementById('back-btn')) {\n"
        "    document.getElementById('back-btn').onclick = backFn\n"
        "      ? backFn\n"
        "      : () => { state.drillTarget = null; renderView(); };\n"
        "  }\n",
        "  if (document.getElementById('back-btn')) {\n"
        "    document.getElementById('back-btn').onclick = backFn\n"
        "      ? backFn\n"
        "      : () => {\n"
        "          // Tweak 8: if we drilled in from home, back returns to home.\n"
        "          if (state.drillOrigin === 'home') {\n"
        "            state.drillOrigin = null;\n"
        "            state.drillTarget = null;\n"
        "            setView('home');\n"
        "          } else {\n"
        "            state.drillTarget = null;\n"
        "            renderView();\n"
        "          }\n"
        "        };\n"
        "  }\n",
        'tweak8.back-btn-handler',
    )

    # The back button label should also reflect where we came from.
    html = must_replace(
        html,
        "  const backBtn = hasBack ? `\n"
        "    <button class=\"back-btn\" id=\"back-btn\">\n"
        "      <svg width=\"14\" height=\"14\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2.5\" viewBox=\"0 0 24 24\"><polyline points=\"15 18 9 12 15 6\"/></svg>\n"
        "      ${backLabel || 'Back'}\n"
        "    </button>` : '';\n",
        "  // Tweak 8: when drilling from home, back-button reads 'Home'.\n"
        "  const defaultBackLabel = (state.drillOrigin === 'home' && !backFn) ? 'Home' : 'Back';\n"
        "  const backBtn = hasBack ? `\n"
        "    <button class=\"back-btn\" id=\"back-btn\">\n"
        "      <svg width=\"14\" height=\"14\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2.5\" viewBox=\"0 0 24 24\"><polyline points=\"15 18 9 12 15 6\"/></svg>\n"
        "      ${backLabel || defaultBackLabel}\n"
        "    </button>` : '';\n",
        'tweak8.back-btn-label',
    )

    return html


# ---------------------------------------------------------------------------
# Tweak 3 - artist names tappable as links
# ---------------------------------------------------------------------------

def tweak3_clickable_artist(html: str) -> str:
    # Add a small CSS block for the new clickable-artist class. Insert it just
    # before the existing #empty-state styles - a stable, unique anchor.
    html = must_replace(
        html,
        "/* ═══════════════════════════════════\n"
        "   EMPTY STATE\n"
        "═══════════════════════════════════ */\n"
        "#empty-state {",
        "/* === Tappable artist links (April 2026 tweaks) === */\n"
        ".clickable-artist {\n"
        "  cursor: pointer;\n"
        "  transition: color 0.12s;\n"
        "  -webkit-tap-highlight-color: transparent;\n"
        "}\n"
        ".clickable-artist:hover { color: var(--accent); text-decoration: underline; text-underline-offset: 3px; }\n"
        ".album-hero-artist.clickable-artist { display: inline-block; }\n"
        ".card-sublabel .clickable-artist { color: inherit; }\n"
        "\n"
        "/* ═══════════════════════════════════\n"
        "   EMPTY STATE\n"
        "═══════════════════════════════════ */\n"
        "#empty-state {",
        'tweak3.css',
    )

    # Album hero on track-list view: wrap the artist name in a clickable span.
    # This is the artist line under the album title in the album drill-down.
    html = must_replace(
        html,
        "        ${state.drillTarget.artist ? `<div class=\"album-hero-artist\">${esc(state.drillTarget.artist)}</div>` : ''}\n",
        "        ${state.drillTarget.artist ? `<div class=\"album-hero-artist clickable-artist\" data-artist=\"${esc(state.drillTarget.artist)}\">${esc(state.drillTarget.artist)}</div>` : ''}\n",
        'tweak3.album-hero',
    )

    # Albums grid: card sublabels show the artist name. Wrap that in a span
    # too. The template literal there builds two variations (with/without
    # mobile download button), and the artist appears in a <span> on each.
    # Replace the desktop variant first (the simpler shape - just the name).
    html = must_replace(
        html,
        "      <div class=\"card-sublabel\" style=\"display:flex;align-items:center;justify-content:space-between\">\n"
        "        <span>${esc(info.artist)}</span>\n",
        "      <div class=\"card-sublabel\" style=\"display:flex;align-items:center;justify-content:space-between\">\n"
        "        <span class=\"clickable-artist\" data-artist=\"${esc(info.artist)}\">${esc(info.artist)}</span>\n",
        'tweak3.album-card-sublabel',
    )

    # Wire up the clickable-artist class with a delegated click handler.
    # Easiest place is the global click listener for the context menu - we
    # piggyback before that runs. We add a fresh listener instead of editing
    # the existing one, to keep the change surgical.
    html = must_replace(
        html,
        "function hideCtxMenu() { ctxMenu.style.display = 'none'; }\n"
        "document.addEventListener('click', (e) => { if (!ctxMenu.contains(e.target)) hideCtxMenu(); });",
        "function hideCtxMenu() { ctxMenu.style.display = 'none'; }\n"
        "document.addEventListener('click', (e) => { if (!ctxMenu.contains(e.target)) hideCtxMenu(); });\n"
        "\n"
        "// Tweak 3: clickable-artist delegated handler. Drills into the artist\n"
        "// view from anywhere the class appears (album hero, album card sublabel,\n"
        "// future surfaces). Stops the click bubbling so we don't also trigger\n"
        "// the album/card click sitting underneath.\n"
        "document.addEventListener('click', (e) => {\n"
        "  const el = e.target.closest('.clickable-artist');\n"
        "  if (!el) return;\n"
        "  const artist = el.dataset.artist;\n"
        "  if (!artist) return;\n"
        "  e.stopPropagation();\n"
        "  e.preventDefault();\n"
        "  // Treat this as a fresh top-level navigation. setView clears\n"
        "  // drillOrigin, so back from the artist page lands on Artists.\n"
        "  setView('artists');\n"
        "  state.drillTarget = { type: 'artist', value: artist };\n"
        "  renderView();\n"
        "});",
        'tweak3.click-handler',
    )

    return html


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def main() -> None:
    src_path = Path(sys.argv[1] if len(sys.argv) > 1 else 'sonata-pwa.html')
    if not src_path.exists():
        raise SystemExit(f"Source file not found: {src_path}")

    backup_path = src_path.with_name(src_path.stem + '.backup-round1.html')
    shutil.copy(src_path, backup_path)
    print(f"[backup] {backup_path}")

    html = src_path.read_text(encoding='utf-8')
    print(f"[input ] {len(html):,} bytes")

    # Order matters: tweak 6 should run before tweak 8 so we don't clash on
    # the search-input replacement anchor. Tweak 1's anchor lives inside the
    # tweak 8 home-card patch, so they're combined there. Tweak 3 last - its
    # anchors are independent.
    html = tweak6_remove_all_tracks(html)
    html = tweak8_back_to_home(html)
    html = tweak3_clickable_artist(html)

    src_path.write_text(html, encoding='utf-8')
    print(f"[output] {len(html):,} bytes -> {src_path}")
    print()
    print("Round 1 complete. Reload Sonata to see the changes.")
    print("If anything looks wrong, restore from the backup file above.")


if __name__ == '__main__':
    main()
