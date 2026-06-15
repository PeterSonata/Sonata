#!/usr/bin/env python3
"""
sonata_cacheboot_serverurl.py

Fix: on a warm boot the iPhone PWA loads the library from the IndexedDB cache via
loadCachedLibrary(), which sets jellyfin.connected = true but never calls
resolveServerUrl(). serverUrl is therefore left empty, so Quick Refresh reports
"Connect to the bridge first" and any stream/art URL rebuilt at render time points
at the wrong origin. This inserts a single resolveServerUrl() call on the cache path.

Conventions: idempotent (marker check), timestamped backup, newline-preserving,
loud failure on a missing or non-unique anchor. Run from the repo root.

    python scripts\\sonata_cacheboot_serverurl.py
"""

import sys
import shutil
from datetime import datetime
from pathlib import Path

TARGET = Path("sonata-pwa.html")
MARKER = "sonata-cacheboot-serverurl"

# Anchor is the two-line block unique to loadCachedLibrary(). Matched with \n;
# the original newline convention is detected and restored on write.
ANCHOR = (
    "    state.tracks = [...saved, ...all];\n"
    "    jellyfin.connected = true;\n"
)

INSERT = (
    "    state.tracks = [...saved, ...all];\n"
    "    jellyfin.connected = true;\n"
    "    await resolveServerUrl();   // " + MARKER + ": set serverUrl on cache boot so Quick Refresh and stream/art URLs work\n"
)


def fail(msg):
    print("ABORT: " + msg)
    sys.exit(1)


def main():
    if not TARGET.exists():
        fail(f"{TARGET} not found. Run this from the repo root.")

    raw = TARGET.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        fail(f"could not decode {TARGET} as UTF-8: {e}")

    # Detect newline convention, then normalise to \n for matching.
    newline = "\r\n" if "\r\n" in text else "\n"
    norm = text.replace("\r\n", "\n")

    if MARKER in norm:
        print("Already patched (marker present). No change made.")
        return

    count = norm.count(ANCHOR)
    if count == 0:
        fail("anchor block not found. Has loadCachedLibrary() changed?")
    if count > 1:
        fail(f"anchor block is not unique ({count} matches). Refusing to guess.")

    patched = norm.replace(ANCHOR, INSERT, 1)

    if patched.count(MARKER) != 1:
        fail("post-patch sanity check failed: marker count is not exactly 1.")

    # Timestamped backup of the original bytes.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = TARGET.with_suffix(TARGET.suffix + f".bak-{stamp}")
    shutil.copy2(TARGET, backup)

    # Restore the original newline convention on write.
    out = patched.replace("\n", newline) if newline == "\r\n" else patched
    TARGET.write_bytes(out.encode("utf-8"))

    print(f"Patched {TARGET}")
    print(f"Backup  {backup}")
    print("Inserted: await resolveServerUrl(); on the cache boot path.")


if __name__ == "__main__":
    main()
