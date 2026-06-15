#!/usr/bin/env python3
"""
genre_audit.py  (READ ONLY)

Scans the music library and reports every distinct genre tag and how many tracks
carry it, so the normalise mapping can be built from what is actually there
rather than guessed. Writes nothing to your files.

Reads MP3, FLAC, M4A, OGG, OPUS, WMA and AAC via mutagen's uniform tag
interface, so one pass covers every format.

Output:
  - Prints a summary and the most common genres to the console.
  - Writes genre_counts.csv  (genre, count) sorted most-common first.
  - Writes genre_blank.csv    (paths of tracks with no genre tag), if any.

Usage (Windows, library mapped to Y:):
    python genre_audit.py Y:\\
Or point it anywhere:
    python genre_audit.py "/volume1/music"
Defaults to Y:\\ if no path is given.

Requires: pip install mutagen
"""

import sys
import csv
import os
from collections import Counter
from pathlib import Path

try:
    import mutagen
except ImportError:
    print("mutagen is not installed. Run:  pip install mutagen")
    sys.exit(1)

AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".m4b", ".ogg", ".opus", ".wma", ".aac"}


def read_genres(path):
    """Return a list of genre strings for one file, or None if unreadable."""
    try:
        f = mutagen.File(path, easy=True)
        if f is None:
            return None
        vals = f.get("genre")
        if not vals:
            return []
        # mutagen returns a list; split anything that is itself multi-valued
        out = []
        for v in vals:
            for part in str(v).split(";"):
                part = part.strip()
                if part:
                    out.append(part)
        return out
    except Exception:
        return None


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("Y:\\")
    if not root.exists():
        print("Path not found: %s" % root)
        sys.exit(1)

    counts = Counter()
    blank = []
    total = 0
    multi = 0
    unreadable = 0

    print("Scanning %s ..." % root)
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if Path(fn).suffix.lower() not in AUDIO_EXTS:
                continue
            total += 1
            full = os.path.join(dirpath, fn)
            genres = read_genres(full)
            if genres is None:
                unreadable += 1
                continue
            if not genres:
                blank.append(full)
                continue
            if len(genres) > 1:
                multi += 1
            for g in genres:
                counts[g] += 1
            if total % 5000 == 0:
                print("  ...%d files" % total)

    # Write the counts CSV
    with open("genre_counts.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["genre", "count"])
        for genre, n in counts.most_common():
            w.writerow([genre, n])

    if blank:
        with open("genre_blank.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["path"])
            for p in blank:
                w.writerow([p])

    # Console summary
    print("")
    print("Audio files scanned : %d" % total)
    print("Distinct genres     : %d" % len(counts))
    print("Tracks tagged       : %d" % (total - len(blank) - unreadable))
    print("Blank genre         : %d" % len(blank))
    print("Multi-genre tracks  : %d" % multi)
    print("Unreadable          : %d" % unreadable)
    print("")
    print("Most common genres:")
    for genre, n in counts.most_common(40):
        print("  %6d  %s" % (n, genre))
    print("")
    print("Full list written to genre_counts.csv (%d rows)." % len(counts))
    if blank:
        print("Blank-genre paths written to genre_blank.csv (%d rows)." % len(blank))


if __name__ == "__main__":
    main()
