# sonata_remove_mini_player.py
# ============================================================
# Removes the floating desktop mini player injected by
# sonata_mini_player.py. Deletes both the JS block and the
# HTML/CSS block cleanly, leaving no orphaned references.
#
# Usage (from repo root):
#   python scripts\sonata_remove_mini_player.py
# ============================================================

import shutil
from datetime import datetime
from pathlib import Path

SOURCE = Path('sonata-pwa.html')
BACKUP_SUFFIX = datetime.now().strftime('%Y%m%d-%H%M%S')
BACKUP = SOURCE.with_name(f'sonata-pwa.backup-{BACKUP_SUFFIX}.html')

IDEMPOTENCY_MARKER = '<!-- sonata-mini-player-removed -->'

JS_START  = '\n// ── Sonata mini player (injected by sonata_mini_player.py) ──────────────────\n'
JS_END    = '\n// ── End Sonata mini player ───────────────────────────────────────────────────\n'

HTML_START = '\n<!-- ======================================================\n     Sonata mini player  (injected by sonata_mini_player.py)\n     ====================================================== -->\n'
HTML_END   = '\n<!-- End Sonata mini player -->\n'


def remove_block(html, start_marker, end_marker, label):
    start = html.find(start_marker)
    if start == -1:
        raise ValueError(f'{label} start marker not found')
    end = html.find(end_marker, start)
    if end == -1:
        raise ValueError(f'{label} end marker not found')
    end += len(end_marker)
    return html[:start] + html[end:]


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(f'Source file not found: {SOURCE}')

    html = SOURCE.read_text(encoding='utf-8')

    if IDEMPOTENCY_MARKER in html:
        print('SKIP: mini player already removed. Nothing to do.')
        return

    if JS_START not in html:
        print('SKIP: mini player JS block not found — may not have been applied.')
        return

    shutil.copy2(SOURCE, BACKUP)
    print(f'Backup: {BACKUP}')

    html = remove_block(html, JS_START,   JS_END,   'JS block')
    html = remove_block(html, HTML_START, HTML_END, 'HTML/CSS block')

    # Leave a marker so the idempotency check works.
    html = html.replace('</body>', '<!-- sonata-mini-player-removed -->\n</body>', 1)

    SOURCE.write_text(html, encoding='utf-8')
    print('Done. Floating mini player removed.')
    print()
    print('Next steps:')
    print('  git add sonata-pwa.html scripts\\sonata_remove_mini_player.py')
    print('  git commit -m "Remove floating desktop mini player"')
    print('  git push')


if __name__ == '__main__':
    main()
