#!/usr/bin/env python3
"""
genre_worklist.py  (READ ONLY)

Builds a per-album worklist so you can assign genres by hand in a spreadsheet,
which is the only honest way to handle the thousands of untagged albums (nothing
can guess a genre for a blank tag).

Groups every audio file by its album folder and writes genre_worklist.csv with
one row per album:

    folder, album_artist, album, current_genre, tracks, new_genre

current_genre is the most common genre tag found across the album's tracks, or
blank where there is none. new_genre is left empty for you to fill in. Open it in
Excel, sort by current_genre so the blanks cluster, fill or correct the new_genre
column, and save. The apply script (next) writes whatever you put in new_genre
back to every track in that folder, and leaves rows you left blank untouched.

Writes nothing to your audio files.

Usage:
    python genre_worklist.py Y:\\
Defaults to Y:\\ if no path is given. Requires: pip install mutagen
"""

import sys
import csv
import os
from collections import Counter, defaultdict
from pathlib import Path

try:
    import mutagen
except ImportError:
    print("mutagen is not installed. Run:  python -m pip install mutagen")
    sys.exit(1)

AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".m4b", ".ogg", ".opus", ".wma", ".aac"}


def first_tag(f, key):
    """First non-empty value for a tag key, or '' ."""
    try:
        vals = f.get(key)
    except Exception:
        return ""
    if not vals:
        return ""
    return str(vals[0]).strip()


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("Y:\\")
    if not root.exists():
        print("Path not found: %s" % root)
        sys.exit(1)

    # folder -> lists of tag values
    albums = defaultdict(lambda: {"artist": Counter(), "albumartist": Counter(),
                                   "album": Counter(), "genre": Counter(), "tracks": 0})
    total = 0
    unreadable = 0

    print("Scanning %s ..." % root)
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if Path(fn).suffix.lower() not in AUDIO_EXTS:
                continue
            total += 1
            full = os.path.join(dirpath, fn)
            try:
                f = mutagen.File(full, easy=True)
                if f is None:
                    unreadable += 1
                    continue
            except Exception:
                unreadable += 1
                continue
            a = albums[dirpath]
            a["tracks"] += 1
            artist = first_tag(f, "artist")
            albumartist = first_tag(f, "albumartist")
            album = first_tag(f, "album")
            genre = first_tag(f, "genre")
            if artist:      a["artist"][artist] += 1
            if albumartist: a["albumartist"][albumartist] += 1
            if album:       a["album"][album] += 1
            if genre:       a["genre"][genre] += 1
            if total % 5000 == 0:
                print("  ...%d files" % total)

    def top(counter, fallback=""):
        return counter.most_common(1)[0][0] if counter else fallback

    rows = []
    for folder, a in albums.items():
        album_artist = top(a["albumartist"]) or top(a["artist"])
        album = top(a["album"]) or os.path.basename(folder)
        current_genre = top(a["genre"])           # blank if none tagged
        rows.append([folder, album_artist, album, current_genre, a["tracks"], ""])

    # Sort so blanks cluster first, then by current genre, artist, album.
    rows.sort(key=lambda r: (r[3] != "", r[3].lower(), r[1].lower(), r[2].lower()))

    with open("genre_worklist.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["folder", "album_artist", "album", "current_genre", "tracks", "new_genre"])
        w.writerows(rows)

    blank = sum(1 for r in rows if r[3] == "")
    print("")
    print("Audio files scanned : %d" % total)
    print("Albums (folders)    : %d" % len(rows))
    print("Albums with a genre : %d" % (len(rows) - blank))
    print("Albums with none    : %d" % blank)
    print("Unreadable files    : %d" % unreadable)
    print("")
    print("Worklist written to genre_worklist.csv (%d album rows)." % len(rows))
    print("Fill the new_genre column, then run the apply script.")


if __name__ == "__main__":
    main()
