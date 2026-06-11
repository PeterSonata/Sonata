#!/usr/bin/env python3
"""
patch_remove_album_nav.py

Removes the Albums entry from the navigation (desktop sidebar and mobile bottom
nav). The albums view itself is left in place, because search album tiles and the
artist drill-downs still render album pages through it. This only closes the
doorway to the master A-Z grid, which is redundant: discovery lives on Home
(daily picks, reshuffle, Quickfire) and finding a specific album lives in Search.

Each nav entry is replaced with an HTML comment breadcrumb. Nav highlighting
iterates over whatever items exist, so removing one is safe even when
currentView becomes 'albums' from a search drill-down.

Standalone: independent of the search patches. Safe to run repeatedly:
idempotent on the marker 'sonata-no-album-nav'. Creates a timestamped backup.
Fails loudly if either anchor is missing or ambiguous.

Run from the repo root:
    cd C:\\Users\\peter\\repos\\sonata
    python scripts\\patch_remove_album_nav.py
"""

import sys
import datetime
from pathlib import Path

TARGET = Path("sonata-pwa.html")
MARKER = "sonata-no-album-nav"


def die(msg):
    print("ABORT: " + msg)
    sys.exit(1)


def apply(text, old, new, label):
    n = text.count(old)
    if n == 0:
        die("anchor not found: " + label)
    if n > 1:
        die("anchor matched %d times (expected exactly 1): %s" % (n, label))
    return text.replace(old, new)


def main():
    if not TARGET.exists():
        die("%s not found. Run from the repo root." % TARGET)

    text = TARGET.read_text(encoding="utf-8")  # CRLF -> LF in memory on Windows

    if MARKER in text:
        print("Already patched (marker present). Nothing to do.")
        return

    # ---- Desktop sidebar entry ----
    desktop_old = (
        '      <div class="nav-item" data-view="albums">\n'
        '        <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>\n'
        '        Albums\n'
        '      </div>'
    )
    desktop_new = (
        '      <!-- ' + MARKER + ': Albums removed from nav; the albums view is kept for search results and artist drill-downs -->'
    )
    text = apply(text, desktop_old, desktop_new, "desktop Albums nav item")

    # ---- Mobile bottom-nav entry ----
    mobile_old = (
        '    <div class="bnav-item" data-view="albums">\n'
        '      <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>\n'
        '      Albums\n'
        '    </div>'
    )
    mobile_new = '    <!-- ' + MARKER + ' (mobile) -->'
    text = apply(text, mobile_old, mobile_new, "mobile Albums bnav item")

    # ---- backup (exact bytes) + write ----
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = TARGET.with_name(TARGET.name + ".bak-" + stamp)
    backup.write_bytes(TARGET.read_bytes())
    TARGET.write_text(text, encoding="utf-8")  # \n -> CRLF on Windows

    print("Patched %s" % TARGET)
    print("Backup  %s" % backup)


if __name__ == "__main__":
    main()
