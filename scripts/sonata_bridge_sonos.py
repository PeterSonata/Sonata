#!/usr/bin/env python3
# scripts/sonata_bridge_sonos.py
# ============================================================
# Mounts routes/sonos.js into the bridge's server.js.
#
# Inserts one line:
#     app.use(require('./routes/sonos'));
# directly after the playlists router mount, keeping it in the
# routes block below the JSON body parser (NOT up by the Jellyfin
# proxy, which must stay above the parser).
#
# Conventions, matching the photo-cache patcher:
#   - run from the repo root, not from scripts/
#   - idempotent: re-running is a no-op
#   - timestamped backup of server.js before writing
#   - fails loud if the anchor is missing or not unique
#   - LF anchors, since read_text() normalises CRLF to LF
# ============================================================

import sys
from datetime import datetime
from pathlib import Path

SERVER = Path('bridge/server.js')

# The line we add.
MOUNT = "app.use(require('./routes/sonos'));"

# Anchor: the playlists mount recorded in the 9 June evening
# session. We insert immediately after this line.
ANCHOR = "app.use(require('./routes/playlists'));"


def fail(msg):
    print(f"ABORT: {msg}")
    sys.exit(1)


def main():
    if not SERVER.exists():
        fail(f"{SERVER} not found. Run from the repo root.")

    text = SERVER.read_text(encoding='utf-8')

    # Idempotency: already mounted?
    if MOUNT in text:
        print("Already mounted. Nothing to do.")
        return

    # Anchor must exist exactly once.
    count = text.count(ANCHOR)
    if count == 0:
        fail(f"anchor not found: {ANCHOR!r}")
    if count > 1:
        fail(f"anchor found {count} times, expected exactly 1: {ANCHOR!r}")

    # Preserve the anchor line's leading whitespace for the new line.
    lines = text.split('\n')
    insert_at = None
    indent = ''
    for i, line in enumerate(lines):
        if ANCHOR in line:
            insert_at = i + 1
            indent = line[:len(line) - len(line.lstrip())]
            break

    if insert_at is None:
        fail("anchor matched in text but not located by line. Aborting.")

    lines.insert(insert_at, f"{indent}{MOUNT}")
    new_text = '\n'.join(lines)

    # Backup before writing.
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = SERVER.with_suffix(f'.js.backup-{stamp}')
    backup.write_text(text, encoding='utf-8')
    print(f"Backup written: {backup}")

    SERVER.write_text(new_text, encoding='utf-8')
    print(f"Mounted sonos router after the playlists mount in {SERVER}.")
    print("Next: scp the two new files to the NAS and restart the bridge.")


if __name__ == '__main__':
    main()
