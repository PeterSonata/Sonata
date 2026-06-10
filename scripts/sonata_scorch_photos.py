#!/usr/bin/env python3
"""
sonata_scorch_photos.py

Removes artist photography entirely. Reverts the Artists grid, the artist page
and search results to Mondrian canvases only. Deletes the fanart.tv/MusicBrainz
client machinery, the Settings "Artist Photography" section, and the mount-time
fetch loop that re-queried uncached artists on every visit (the cause of the
photos-reload-on-every-visit annoyance).

This is pure subtraction. The file ends smaller than it started.

Decided 9 June 2026: a wall of photos reads like any other media app, and the
auto-matches were too often wrong (Beethoven on an obscure singer, Al Green on
Al Naayfish). A uniform Mondrian wall treats every artist with equal weight,
which fits Sonata's character. The bridge-side photo cache stays in git history
if ever wanted again, but the client no longer uses it.

Behaviour, matching the other Sonata patchers:
  - Idempotent: if the photo CSS is already gone, it makes no change.
  - Timestamped backup before writing.
  - Fails loud if any anchor is missing or not unique. No silent half-edit.
  - Uses \n anchors (Python normalises CRLF to LF on read).
"""

import sys
import time
from pathlib import Path

TARGET = Path("sonata-pwa.html")

# Each entry: (description, exact_text_to_remove). All are deletions.
REMOVALS = []

# 1. CSS: the .artist-photo rules. Remove the whole block from the first
#    .card-art .artist-photo selector through the end of .artist-photo-loading.
REMOVALS.append((
    "CSS .artist-photo rules",
    """.card-art .artist-photo {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  opacity: 0;
  transition: opacity 0.4s;
}
.card-art .artist-photo.loaded { opacity: 1; }
.card-art .artist-photo-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
"""
))

# Note: the .artist-photo-loading block has more lines after justify-content.
# Rather than guess its full extent, we close it precisely below by removing
# from its opening through its closing brace. Handled as a second targeted cut.

def main():
    if not TARGET.exists():
        die(f"{TARGET} not found. Run from the repo root.")

    src = TARGET.read_text(encoding="utf-8")

    # Idempotency check: if the core photo function block is gone, assume done.
    if "ARTIST PHOTOGRAPHY (fanart.tv + MusicBrainz)" not in src:
        print("Already scorched: artist photography block not present. No change.")
        return

    new = src

    # ── 1. CSS block: from `.card-art .artist-photo {` up to but not including
    #       the next real rule after the loading spinner. We cut from the
    #       opening selector to the `.card-art canvas` line is BEFORE it, so we
    #       anchor on the opening and the known following selector instead.
    css_start = "\n.card-art .artist-photo {\n"
    # The rule immediately following the photo CSS in the file:
    css_end_anchor = None
    for candidate in [
        "\n.card-art .artist-photo-loading {\n",
    ]:
        if candidate in new:
            css_end_anchor = candidate
            break

    # We remove from css_start through the close of the .artist-photo-loading
    # rule. Find the loading rule and its closing brace.
    s_idx = new.find(css_start)
    if s_idx == -1:
        die("CSS anchor `.card-art .artist-photo {` not found.")
    load_idx = new.find(".card-art .artist-photo-loading {", s_idx)
    if load_idx == -1:
        die("CSS anchor `.card-art .artist-photo-loading {` not found.")
    close_idx = new.find("}", load_idx)
    if close_idx == -1:
        die("Could not find closing brace of .artist-photo-loading rule.")
    # Remove from the newline before css_start through the closing brace + newline.
    # s_idx points at the leading \n of css_start; cut through close_idx inclusive.
    end_cut = close_idx + 1
    # also swallow a trailing newline if present
    if end_cut < len(new) and new[end_cut] == "\n":
        end_cut += 1
    removed_css = new[s_idx:end_cut]
    if ".artist-photo" not in removed_css or "artist-photo-loading" not in removed_css:
        die("CSS removal span looks wrong, aborting.")
    new = new[:s_idx] + new[end_cut:]
    print("Removed: CSS .artist-photo / .artist-photo-loading rules.")

    # ── 2. Render site 1, Artists grid: the cache read, the photoEl, the
    #       canvas+photo markup, and the mount-time fetch loop.
    r1_cache = "  const filtered = Object.entries(map).filter(([,v]) => v.count > 1);\n  const photoCache = loadArtistCache();\n"
    r1_cache_new = "  const filtered = Object.entries(map).filter(([,v]) => v.count > 1);\n"
    new = replace_unique(new, r1_cache, r1_cache_new, "Artists grid: cache read")

    r1_map = """  const cards = filtered.sort((a,b) => a[0].localeCompare(b[0])).map(([name, info]) => {
    const cachedImg = photoCache[name];
    const photoEl  = cachedImg ? `<img class="artist-photo loaded" src="${esc(cachedImg)}" alt="${esc(name)}">` : '';
    return `
    <div class="grid-card" data-artist="${esc(name)}">
      <div class="card-art">
        <canvas class="art-canvas" data-seed="${esc(info.seed)}" data-size="160"></canvas>
        ${photoEl}
      </div>"""
    r1_map_new = """  const cards = filtered.sort((a,b) => a[0].localeCompare(b[0])).map(([name, info]) => {
    return `
    <div class="grid-card" data-artist="${esc(name)}">
      <div class="card-art">
        <canvas class="art-canvas" data-seed="${esc(info.seed)}" data-size="160"></canvas>
      </div>"""
    new = replace_unique(new, r1_map, r1_map_new, "Artists grid: card markup")

    r1_loop = """  initArtCanvases();

  if (jellyfin.bridgeUrl) {
    filtered.forEach(([name]) => {
      if (photoCache[name] === undefined) fetchAndCacheArtistImage(name);
    });
  }
"""
    r1_loop_new = """  initArtCanvases();
"""
    new = replace_unique(new, r1_loop, r1_loop_new, "Artists grid: mount-time fetch loop")

    # ── 3. Render site 2, artist page hero.
    r2_cache = """  const photoCache = loadArtistCache();
  const cachedImg  = photoCache[artistName];
  const photoEl    = cachedImg ? `<img class="artist-photo loaded" src="${esc(cachedImg)}" alt="${esc(artistName)}">` : '';

  const cards = albums.map(info => `"""
    r2_cache_new = """  const cards = albums.map(info => `"""
    new = replace_unique(new, r2_cache, r2_cache_new, "Artist page: cache read")

    r2_hero = """        <div class="artist-albums-photo">
          <canvas class="art-canvas" data-seed="${esc(artistName)}" data-size="80"></canvas>
          ${photoEl}
        </div>"""
    r2_hero_new = """        <div class="artist-albums-photo">
          <canvas class="art-canvas" data-seed="${esc(artistName)}" data-size="80"></canvas>
        </div>"""
    new = replace_unique(new, r2_hero, r2_hero_new, "Artist page: hero photo")

    # ── 4. Render site 3, search results.
    r3_cache = """  const matchedTracks = allMatchedTracks.slice(0, 100);

  const photoCache = loadArtistCache();

  let html = `"""
    r3_cache_new = """  const matchedTracks = allMatchedTracks.slice(0, 100);

  let html = `"""
    new = replace_unique(new, r3_cache, r3_cache_new, "Search: cache read")

    r3_map = """    const cards = matchedArtists.map(([name, info]) => {
      const cachedImg = photoCache[name];
      const photoEl  = cachedImg ? `<img class="artist-photo loaded" src="${esc(cachedImg)}" alt="${esc(name)}">` : '';
      return `
      <div class="grid-card search-artist-card" data-artist="${esc(name)}">
        <div class="card-art">
          <canvas class="art-canvas" data-seed="${esc(info.seed)}" data-size="160"></canvas>
          ${photoEl}
        </div>"""
    r3_map_new = """    const cards = matchedArtists.map(([name, info]) => {
      return `
      <div class="grid-card search-artist-card" data-artist="${esc(name)}">
        <div class="card-art">
          <canvas class="art-canvas" data-seed="${esc(info.seed)}" data-size="160"></canvas>
        </div>"""
    new = replace_unique(new, r3_map, r3_map_new, "Search: card markup")

    # ── 5. The whole photo function block, from the banner comment through the
    #       two onclick wirings, up to (not including) the LIBRARY CACHE banner.
    block_start = "\n// ══════════════════════════════════════════════\n//  ARTIST PHOTOGRAPHY (fanart.tv + MusicBrainz)\n// ══════════════════════════════════════════════\n"
    block_end_marker = "// ══════════════════════════════════════════════\n//  LIBRARY CACHE (IndexedDB)\n"
    bs = new.find(block_start)
    be = new.find(block_end_marker)
    if bs == -1:
        die("photo function block start banner not found.")
    if be == -1:
        die("LIBRARY CACHE banner (block end marker) not found.")
    if be < bs:
        die("block markers out of order, aborting.")
    removed_block = new[bs:be]
    if "fetchAndCacheArtistImage" not in removed_block or "fetchAllArtistPhotos" not in removed_block:
        die("photo function block span looks wrong, aborting.")
    new = new[:bs] + "\n" + new[be:]
    print("Removed: artist photography function block (loadArtistCache, fetch, inject, fetchAll, etc).")

    # ── 6. Settings "Artist Photography" section.
    settings_start = '\n    <div class="settings-section-label" style="margin-top:0;border-top:var(--bw) solid var(--border)">Artist Photography</div>\n'
    ss = new.find(settings_start)
    if ss == -1:
        die("Settings Artist Photography section start not found.")
    # The section is one outer <div ...> ... </div> following the label. End it
    # at the fanart-fetch-progress div's close, which is the last line before
    # the section's closing </div>. Anchor on the progress div + its closer.
    settings_tail = '      <div id="fanart-fetch-progress" style="display:none;font-size:10px;font-family:\'IBM Plex Mono\',monospace;color:var(--text3);letter-spacing:0.08em;margin-top:8px"></div>\n    </div>\n'
    st = new.find(settings_tail, ss)
    if st == -1:
        die("Settings Artist Photography section end (fetch-progress div) not found.")
    end_settings = st + len(settings_tail)
    removed_settings = new[ss:end_settings]
    if "Artist Photography" not in removed_settings or "fanart-fetch-all-btn" not in removed_settings:
        die("Settings section span looks wrong, aborting.")
    new = new[:ss] + "\n" + new[end_settings:]
    print("Removed: Settings Artist Photography section.")

    # ── 7. The stray init call to updateFanartStatus().
    stray = "\n// Fanart status (no key input anymore — bridge holds the key)\nupdateFanartStatus();\n"
    if stray in new:
        new = new.replace(stray, "\n", 1)
        print("Removed: stray updateFanartStatus() init call.")
    else:
        # Try a looser match in case the comment wording differs.
        loose = "updateFanartStatus();\n"
        if new.count(loose) == 1:
            new = new.replace(loose, "", 1)
            print("Removed: stray updateFanartStatus() init call (loose match).")
        else:
            die("stray updateFanartStatus() init call not found uniquely. "
                "Aborting so init does not throw a ReferenceError.")

    # Sanity: no dangling references to the removed functions should remain.
    for ref in ["loadArtistCache", "fetchAndCacheArtistImage", "getArtistImageUrl",
                "injectArtistPhoto", "updateFanartStatus", "fetchAllArtistPhotos",
                "saveArtistCache", "loadMbidCache"]:
        if ref in new:
            die(f"dangling reference to {ref} still present after removal. Aborting.")

    if new == src:
        die("No change produced. Aborting.")

    backup = TARGET.with_suffix(f".backup-{time.strftime('%Y%m%d-%H%M%S')}.html")
    backup.write_text(src, encoding="utf-8")
    print(f"\nBackup written: {backup}")

    TARGET.write_text(new, encoding="utf-8")
    saved = len(src) - len(new)
    print(f"Wrote {TARGET}. File is {saved} bytes smaller.")
    print("\nMondrian is now the only artist visual. Deploy by pushing to GitHub Pages,")
    print("then cold-start the iPhone PWA (quit from app switcher, relaunch) and Ctrl+F5 on desktop.")


def replace_unique(haystack, old, new_str, label):
    count = haystack.count(old)
    if count == 0:
        die(f"anchor not found: {label}")
    if count > 1:
        die(f"anchor found {count} times, expected 1: {label}")
    print(f"Removed: {label}.")
    return haystack.replace(old, new_str, 1)


def die(msg):
    print(f"ERROR: {msg}")
    sys.exit(1)


if __name__ == "__main__":
    main()
