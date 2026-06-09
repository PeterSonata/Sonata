#!/usr/bin/env python3
"""
sonata_bridge_photos.py

Wires the new routes/photos.js router into the bridge server.js, and updates
the startup endpoint log line to mention /photos.

This is a bridge-side patcher (server.js), not a client patcher. Run it from
the repo root after dropping routes/photos.js and lib/photostore.js into
bridge/. Then deploy both new files plus the patched server.js to the NAS and
restart PM2 (see the deploy note).

Behaviour, matching the other Sonata patchers:
  - Idempotent: if the router is already mounted, it makes no change.
  - Timestamped backup of server.js before writing.
  - Fails loud if an anchor is missing or not unique. No silent half-edit.
  - Uses \n anchors (Python normalises CRLF to LF on read).
"""

import sys
import time
from pathlib import Path

TARGET = Path("bridge/server.js")

# Mount the photos router right after the playlists router, keeping it in the
# routes block well below the Jellyfin proxy and the body parser.
ANCHOR_MOUNT = "app.use(require('./routes/playlists'));\n"
INJECT_MOUNT = (
    "app.use(require('./routes/playlists'));\n"
    "app.use(require('./routes/photos'));\n"
)
MOUNT_MARKER = "require('./routes/photos')"

# Update the endpoint summary log so the boot banner is honest.
ANCHOR_LOG = (
    "  console.log(`  Endpoints: /health, /stats, /jellyfin/*, /fanart/:mbid, /mbid, /jobs`);\n"
)
INJECT_LOG = (
    "  console.log(`  Endpoints: /health, /stats, /jellyfin/*, /fanart/:mbid, /mbid, /jobs, /playlists, /photos`);\n"
)


def die(msg):
    print(f"ERROR: {msg}")
    sys.exit(1)


def main():
    if not TARGET.exists():
        die(f"{TARGET} not found. Run from the repo root (it contains bridge/).")

    src = TARGET.read_text(encoding="utf-8")

    already_mounted = MOUNT_MARKER in src
    log_done = "/playlists, /photos`" in src

    if already_mounted and log_done:
        print("Already patched: photos router mounted and boot log updated. No change.")
        return

    new = src

    # 1. Mount the router.
    if not already_mounted:
        count = new.count(ANCHOR_MOUNT)
        if count == 0:
            die("mount anchor (playlists require line) not found. Has server.js changed?")
        if count > 1:
            die(f"mount anchor found {count} times, expected 1. Aborting to avoid a wrong edit.")
        new = new.replace(ANCHOR_MOUNT, INJECT_MOUNT, 1)
        print("Patched: mounted routes/photos after routes/playlists.")
    else:
        print("Skipped mount: photos router already present.")

    # 2. Update the boot banner. Non-fatal if the exact line has drifted, since
    #    it is cosmetic, but warn so it is not silently missed.
    if not log_done:
        if ANCHOR_LOG in new:
            new = new.replace(ANCHOR_LOG, INJECT_LOG, 1)
            print("Patched: boot endpoint log now lists /playlists and /photos.")
        else:
            print("WARNING: boot endpoint log line not matched exactly, left as-is. "
                  "Cosmetic only; mount above is what matters.")

    if new == src:
        die("No change produced despite anchors. Aborting rather than writing an identical file.")

    backup = TARGET.with_suffix(f".js.backup-{time.strftime('%Y%m%d-%H%M%S')}")
    backup.write_text(src, encoding="utf-8")
    print(f"Backup written: {backup}")

    TARGET.write_text(new, encoding="utf-8")
    print(f"Wrote {TARGET}.")
    print("\nNext: deploy bridge/routes/photos.js, bridge/lib/photostore.js and the")
    print("patched bridge/server.js to the NAS, then restart PM2. See the deploy note.")


if __name__ == "__main__":
    main()
