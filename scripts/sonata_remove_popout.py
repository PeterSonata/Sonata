#!/usr/bin/env python3
# sonata_remove_popout.py
# ------------------------------------------------------------------
# Removes the desktop pop-out player entirely.
#
# Why: the pop-out button never actually rendered as a usable control.
# It was injected as a stray fourth flex child of #player, placed AFTER
# #vol-area closes (not inside it, despite the 10 June fix recording
# otherwise), and it left an unbalanced extra </div> in the player bar.
# The button markup and its IIFE are present but the feature is dead in
# practice, so this strips it out and rebalances the bar.
#
# Three removals, each anchored uniquely:
#   1. The #popout-btn CSS block.
#   2. The button markup + the stray </div> + the popout-fix marker,
#      collapsing the player-bar tail back to (vol-area close)(player close).
#   3. The whole pop-out IIFE, located by its start/end comment markers.
#      NB: this IIFE is nested inside the outer app IIFE, whose own
#      })(); sits just after the end marker and must be left intact.
#
# Idempotent, timestamped backup, fails loud on a missing or non-unique
# anchor, aborts before writing if any pop-out reference would survive.
# Run from the repo root: python scripts\sonata_remove_popout.py
# ------------------------------------------------------------------

import sys
import shutil
import datetime
from pathlib import Path

HTML = Path('sonata-pwa.html')

CSS_BLOCK = (
    "/* \u2500\u2500 Pop-out button \u2500\u2500 */\n"
    "#popout-btn {\n"
    "  background: none;\n"
    "  border: none;\n"
    "  color: var(--text3);\n"
    "  cursor: pointer;\n"
    "  padding: 8px;\n"
    "  display: flex;\n"
    "  align-items: center;\n"
    "  justify-content: center;\n"
    "  flex-shrink: 0;\n"
    "  margin-left: 4px;\n"
    "  border-radius: 6px;\n"
    "  transition: color 0.12s, background 0.12s;\n"
    "}\n"
    "#popout-btn:hover { color: var(--text); background: var(--surface2); }\n"
    "#popout-btn.popout-open { color: var(--accent); }\n"
)

# Player-bar tail: vol-area close, button, stray div, player close, marker.
# Collapse to: vol-area close, player close.
MARKUP_BLOCK = (
    '  </div>\n'
    '    <button id="popout-btn" title="Pop out player" aria-label="Pop out player">\n'
    '      <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>\n'
    '    </button>\n'
    '  </div>\n'
    '</div>\n'
    '<!-- popout-fix-applied -->\n'
)
MARKUP_REPLACEMENT = (
    '  </div>\n'
    '</div>\n'
)

# IIFE located by stable plain-text markers (avoids anchoring on the
# box-drawing rule characters in the comment lines).
IIFE_START_KEY = 'Sonata pop-out player (injected by sonata_popout_player.py)'
IIFE_END_KEY = 'End Sonata pop-out player'


def die(msg):
    print('ABORT: ' + msg)
    sys.exit(1)


def remove_once(src, block, label):
    n = src.count(block)
    if n == 0:
        die(f'{label} anchor not found.')
    if n > 1:
        die(f'{label} anchor not unique ({n} matches).')
    return src.replace(block, '', 1)


def main():
    if not HTML.exists():
        die(f'{HTML} not found. Run from the repo root.')
    src = HTML.read_text(encoding='utf-8')

    if 'id="popout-btn"' not in src and IIFE_START_KEY not in src:
        print('Already removed (no pop-out references). Nothing to do.')
        return

    # 1. CSS block.
    src = remove_once(src, CSS_BLOCK, 'pop-out CSS')

    # 2. Markup + stray div + marker, rebalanced.
    nm = src.count(MARKUP_BLOCK)
    if nm == 0:
        die('player-bar markup anchor not found.')
    if nm > 1:
        die(f'player-bar markup anchor not unique ({nm} matches).')
    src = src.replace(MARKUP_BLOCK, MARKUP_REPLACEMENT, 1)

    # 3. IIFE, by start/end markers.
    if src.count(IIFE_START_KEY) != 1:
        die('pop-out IIFE start marker not unique.')
    if src.count(IIFE_END_KEY) != 1:
        die('pop-out IIFE end marker not unique.')
    si = src.index(IIFE_START_KEY)
    line_start = src.rfind('\n', 0, si) + 1
    ei = src.index(IIFE_END_KEY, si)
    line_end = src.find('\n', ei)
    line_end = len(src) if line_end == -1 else line_end + 1
    src = src[:line_start] + src[line_end:]

    # Sanity: nothing pop-out related may survive.
    for token in ('popout-btn', 'Sonata pop-out player', 'POPUP_HTML',
                  'SonataPopout', 'sopPlayGenreTrack'):
        if token in src:
            die(f'post-removal check failed, "{token}" still present; not writing.')

    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = HTML.with_suffix(f'.backup-{ts}.html')
    shutil.copy2(HTML, backup)
    HTML.write_text(src, encoding='utf-8')
    print(f'Removed pop-out player from {HTML} (backup: {backup.name}).')
    print('Stripped: CSS block, button markup + stray div, IIFE. Player bar rebalanced.')


if __name__ == '__main__':
    main()
