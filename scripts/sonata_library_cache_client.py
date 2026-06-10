#!/usr/bin/env python3
"""
sonata_library_cache_client.py

Repoints the Sonata PWA boot path at the bridge library cache endpoint.

Before: every boot does an unconditional full per-page Jellyfin re-walk
        (silent, two seconds after the cached render).
After:  boot asks GET /library/version, compares it against the version
        stored in the cache meta, and only pulls GET /library (one slim
        request) when the bridge version has changed. First run pulls the
        whole library from the bridge in one request, falling back to the
        old per-page walk only if the bridge library endpoint is missing.

Idempotent. Creates a timestamped backup. Fails loudly on any missing or
non-unique anchor. Matches the file's existing newline convention. Run from
the repo root:  python scripts\\sonata_library_cache_client.py
"""

import sys
import time
from pathlib import Path

TARGET = Path("sonata-pwa.html")

# ── Injected functions ────────────────────────────────────────────────────────
# Adopt a slim bridge track into the client's full track shape, and the boot
# sync that version-checks the bridge before pulling the whole library.
# Tolerant of either the bridge's resolved "client vocabulary" or raw Jellyfin
# field names, and of duration in seconds or RunTimeTicks, so it stays correct
# whichever projection the bridge emits.
INJECT = """
// ── Bridge library cache (slim pull + version check) ───────────────────────────
function adoptSlimTrack(t) {
  const id          = t.id || t.Id;
  const title       = t.title || t.Name || 'Unknown Title';
  const artist      = t.artist || (t.Artists && t.Artists[0]) || t.AlbumArtist || 'Unknown Artist';
  const albumArtist = t.albumArtist || t.AlbumArtist || artist;
  const rawAlbum    = t.album || t.Album || '';
  const album       = rawAlbum || 'Unknown Album';
  const genre       = t.genre || (t.Genres && t.Genres[0]) || '';
  const trackNumber = (t.trackNumber != null ? t.trackNumber : t.IndexNumber) || 0;
  const duration    = (t.duration != null) ? t.duration
                    : (t.RunTimeTicks ? Math.round(t.RunTimeTicks / 10000000) : 0);
  const year        = (t.year != null ? t.year : t.ProductionYear) || 0;
  const artId       = t.albumId || t.AlbumId || id;
  const artUrl      = `${jellyfin.serverUrl}/Items/${artId}/Images/Primary?maxHeight=300&quality=90`;
  const streamUrl   = `${jellyfin.serverUrl}/Audio/${id}/stream?static=true`;
  return {
    id, jellyfinId: id, title, artist, albumArtist, album, genre,
    trackNumber, duration, year,
    artSeed: rawAlbum || albumArtist || artist || title,
    artUrl, streamUrl, picture: null, file: null, saved: false,
  };
}

// Returns true if the library is now in hand from the bridge, false otherwise.
// On false the caller decides what to do (first run falls back to fetchLibrary;
// the background path simply keeps the cached library).
async function syncLibraryFromBridge(opts = {}) {
  const firstRun = !!opts.firstRun;
  if (!jellyfin.bridgeUrl) return false;
  const base = jellyfin.bridgeUrl;
  try {
    let bridgeVersion = null;

    // Warm path: cheap version probe first, bail out early if unchanged.
    if (!firstRun) {
      const meta = JSON.parse(localStorage.getItem(CACHE_META_KEY) || 'null');
      const vr = await fetch(`${base}/library/version`);
      if (!vr.ok) throw new Error(`version ${vr.status}`);
      const vinfo = await vr.json();
      bridgeVersion = vinfo.version || null;
      if (meta && meta.version && bridgeVersion && meta.version === bridgeVersion) {
        return true; // already current, nothing to pull
      }
    }

    // Pull the whole slim library in one request.
    const lr = await fetch(`${base}/library`);
    if (!lr.ok) throw new Error(`library ${lr.status}`);
    const payload = await lr.json();
    const slim = Array.isArray(payload)
               ? payload
               : (payload.tracks || payload.library || payload.items || []);
    if (!slim.length) throw new Error('empty library payload');

    // serverUrl is needed to build art/stream URLs (cheap, no network).
    await resolveServerUrl();
    if (firstRun) { try { await resolveJellyfinUser(); } catch (e) {} }

    // First run skipped the version probe above; fetch it now for the meta so
    // the next boot can short-circuit.
    if (!bridgeVersion) {
      try {
        const vr2 = await fetch(`${base}/library/version`);
        if (vr2.ok) bridgeVersion = (await vr2.json()).version || null;
      } catch (e) {}
    }

    const adopted = slim.map(adoptSlimTrack);
    const saved   = state.tracks.filter(t => t.saved);
    state.tracks  = [...saved, ...adopted];

    // Re-link any OPFS-saved tracks to fresh art/stream URLs.
    for (const s of saved) {
      const jf = adopted.find(t => t.id === s.id);
      if (jf) { s.artUrl = jf.artUrl; s.streamUrl = jf.streamUrl; }
    }

    jellyfin.connected = true;
    invalidateIndexes();
    buildIndexes();
    localStorage.setItem('sonata_last_refresh', Date.now().toString());
    await saveCachedLibrary(adopted, bridgeVersion);
    updateJfStatus(`Library · ${adopted.length.toLocaleString()} tracks`);
    if (firstRun) { try { await fetchJellyfinPlaylists(); } catch (e) {} }
    renderPlaylists();
    renderView();
    return true;
  } catch (e) {
    console.warn('Bridge library sync failed:', e);
    return false;
  }
}
"""

# ── Anchors and replacements (LF-normalised; the file is read/written CRLF) ─────

# 1. saveCachedLibrary signature gains a version parameter.
SIG_OLD = "async function saveCachedLibrary(tracks) {"
SIG_NEW = "async function saveCachedLibrary(tracks, version) {"

# 2. The cache meta write records the bridge version.
META_OLD = (
    "    localStorage.setItem(CACHE_META_KEY, JSON.stringify({\n"
    "      ts: Date.now(), count: toSave.length,\n"
    "    }));"
)
META_NEW = (
    "    localStorage.setItem(CACHE_META_KEY, JSON.stringify({\n"
    "      ts: Date.now(), count: toSave.length, version: version || null,\n"
    "    }));"
)

# 3. Injection point: immediately after clearLibraryCache().
CLEAR_FN = (
    "async function clearLibraryCache() {\n"
    "  try {\n"
    "    const db = await openCacheDB();\n"
    "    const tx = db.transaction(CACHE_STORE, 'readwrite');\n"
    "    tx.objectStore(CACHE_STORE).clear();\n"
    "    await new Promise((res, rej) => { tx.oncomplete = res; tx.onerror = rej; });\n"
    "    db.close();\n"
    "    localStorage.removeItem(CACHE_META_KEY);\n"
    "  } catch(e) {}\n"
    "}"
)

# 4. The boot block: replace the unconditional re-walk and the first-run walk.
#    NB: the existing comments use em dashes and an ellipsis; matched verbatim.
BOOT_OLD = (
    "    if (fromCache) {\n"
    "      // Library from cache \u2014 render immediately, hide splash (with floor),\n"
    "      // then sync everything silently in background\n"
    "      renderPlaylists();\n"
    "      renderView();\n"
    "      await hideSplash();\n"
    "      setTimeout(async () => {\n"
    "        try {\n"
    "          await fetchLibrary({ silent: true });\n"
    "        } catch(e) { /* keep cached version and localStorage playlists */ }\n"
    "      }, 2000);\n"
    "    } else {\n"
    "      // No cache \u2014 full load (fetchLibrary keeps the splash up via its own\n"
    "      // loading-text updates; we hand off without lowering the floor early)\n"
    "      splashText.textContent = 'first run, fetching everything\u2026';\n"
    "      await fetchLibrary({ keepSplash: true });\n"
    "      renderPlaylists();\n"
    "      renderView();\n"
    "      await hideSplash();\n"
    "    }"
)
BOOT_NEW = (
    "    if (fromCache) {\n"
    "      // Library from cache: render immediately, hide splash (with floor),\n"
    "      // then version-check against the bridge in the background and only\n"
    "      // re-pull the whole library if the bridge version has changed.\n"
    "      renderPlaylists();\n"
    "      renderView();\n"
    "      await hideSplash();\n"
    "      setTimeout(() => { syncLibraryFromBridge({ firstRun: false }); }, 2000);\n"
    "    } else {\n"
    "      // No cache, first run: pull the whole library from the bridge in one\n"
    "      // slim request, falling back to the per-page Jellyfin walk only if the\n"
    "      // bridge library endpoint is unavailable.\n"
    "      splashText.textContent = 'first run, fetching everything\u2026';\n"
    "      const gotFromBridge = await syncLibraryFromBridge({ firstRun: true });\n"
    "      if (!gotFromBridge) await fetchLibrary({ keepSplash: true });\n"
    "      renderPlaylists();\n"
    "      renderView();\n"
    "      await hideSplash();\n"
    "    }"
)


def die(msg):
    print(f"ERROR: {msg}")
    sys.exit(1)


def require_unique(text, anchor, label):
    n = text.count(anchor)
    if n == 0:
        die(f"anchor not found: {label}")
    if n > 1:
        die(f"anchor not unique ({n} matches): {label}")


def main():
    if not TARGET.exists():
        die(f"{TARGET} not found. Run from the repo root.")

    raw = TARGET.read_bytes()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8").replace("\r\n", "\n")

    # Idempotency: bail cleanly if already applied.
    if "function syncLibraryFromBridge" in text:
        print("Already applied (syncLibraryFromBridge present). Nothing to do.")
        return

    # Verify every anchor before touching anything.
    require_unique(text, SIG_OLD, "saveCachedLibrary signature")
    require_unique(text, META_OLD, "cache meta write")
    require_unique(text, CLEAR_FN, "clearLibraryCache function")
    require_unique(text, BOOT_OLD, "boot fromCache/else block")

    # Apply.
    text = text.replace(SIG_OLD, SIG_NEW)
    text = text.replace(META_OLD, META_NEW)
    text = text.replace(CLEAR_FN, CLEAR_FN + "\n" + INJECT)
    text = text.replace(BOOT_OLD, BOOT_NEW)

    # Backup, then write back in the original newline convention.
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = TARGET.with_name(f"{TARGET.name}.backup-{stamp}")
    backup.write_bytes(raw)

    out = text.replace("\n", nl) if nl == "\r\n" else text
    TARGET.write_bytes(out.encode("utf-8"))

    print(f"Patched {TARGET}")
    print(f"Backup written to {backup.name}")
    print("Newline convention:", "CRLF" if nl == "\r\n" else "LF")


if __name__ == "__main__":
    main()
