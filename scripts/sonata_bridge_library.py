#!/usr/bin/env python3
"""
sonata_bridge_library.py

Mounts the /library router into the bridge's server.js and corrects the boot
banner Endpoints line (which also picks up the /sonos entry that was left off
when Sonos was added).

Two edits, both idempotent:
  1. Add  app.use(require('./routes/library'));  after the /photos mount.
  2. Update the banner Endpoints line to list /sonos and /library.

Run from the REPO ROOT, not from scripts/:

    python scripts\\sonata_bridge_library.py

Targets bridge/server.js. Takes a timestamped backup. Reads and writes bytes
so the file's existing LF line endings are preserved exactly (no accidental
CRLF rewrite on Windows). Fails loud and writes nothing if any anchor is
missing or not unique.
"""

import sys
import shutil
import datetime
from pathlib import Path

TARGET = Path('bridge/server.js')


def fail(msg):
    print(f"ABORT: {msg}")
    sys.exit(1)


def main():
    if not TARGET.exists():
        fail(f"{TARGET} not found. Run this from the repo root.")

    raw = TARGET.read_bytes()
    src = raw.decode('utf-8')

    # Match the file's own newline convention so the inserted line does not
    # leave a stray LF in an otherwise-CRLF file (or vice versa).
    nl = '\r\n' if b'\r\n' in raw else '\n'

    # Idempotency: bail cleanly if already mounted.
    if "require('./routes/library')" in src:
        print("Already mounted: ./routes/library is present. Nothing to do.")
        return

    # ── Edit 1: mount line, inserted after the /photos mount ──
    mount_anchor = "app.use(require('./routes/photos'));"
    n = src.count(mount_anchor)
    if n != 1:
        fail(f"mount anchor found {n} times (need exactly 1): {mount_anchor!r}")
    src = src.replace(
        mount_anchor,
        mount_anchor + nl + "app.use(require('./routes/library'));",
    )

    # ── Edit 2: boot banner ──
    # Current banner ends "...playlists, /photos" (the /sonos entry was never
    # added). Rewrite it to include both /sonos and /library.
    banner_anchor = "/playlists, /photos`"
    n = src.count(banner_anchor)
    if n != 1:
        fail(f"banner anchor found {n} times (need exactly 1): {banner_anchor!r}")
    src = src.replace(banner_anchor, "/playlists, /sonos, /photos, /library`")

    # ── Backup + write ──
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = TARGET.with_name(TARGET.name + f'.backup-{ts}')
    shutil.copy2(TARGET, backup)
    TARGET.write_bytes(src.encode('utf-8'))

    print(f"Backup written: {backup}")
    print("Mounted ./routes/library and updated the boot banner.")


if __name__ == '__main__':
    main()
