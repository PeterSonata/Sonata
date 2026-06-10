# sonata_popout_fix.py
# ============================================================
# Fixes the pop-out button visibility.
#
# The original patcher placed the button outside #vol-area,
# where the flex layout gives it no space. This patcher:
#   1. Removes the misplaced button from outside #vol-area.
#   2. Injects it inside #vol-area (after the vol-bar div).
#   3. Moves the CSS from a runtime JS injection into a proper
#      <style> block in the document so it applies immediately.
#
# Usage (from repo root):
#   python scripts\sonata_popout_fix.py
# ============================================================

import shutil
from datetime import datetime
from pathlib import Path

SOURCE = Path('sonata-pwa.html')
BACKUP_SUFFIX = datetime.now().strftime('%Y%m%d-%H%M%S')
BACKUP = SOURCE.with_name(f'sonata-pwa.backup-{BACKUP_SUFFIX}.html')

IDEMPOTENCY_MARKER = '<!-- popout-fix-applied -->'

# The misplaced button to remove (outside vol-area)
OLD_BUTTON = """  <button id="popout-btn" title="Pop out player" aria-label="Pop out player">
    <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
  </button>
</div>

<!-- ═══════ MINI PLAYER (mobile) ═══════ -->"""

# Corrected: button inside vol-area, before closing </div>
NEW_VOL_AREA_END = """    <button id="popout-btn" title="Pop out player" aria-label="Pop out player">
      <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10\" y2="14"/></svg>
    </button>
  </div>
</div>
<!-- popout-fix-applied -->

<!-- ═══════ MINI PLAYER (mobile) ═══════ -->"""

# The runtime CSS injection to remove from JS
OLD_CSS_INJECT = """  // Inject CSS into the page's <head>.
  const style = document.createElement('style');
  style.textContent = `
/* ── Pop-out button (injected by sonata_popout_player.py) ── */
#popout-btn {
  background: none;
  border: none;
  color: var(--text3);
  cursor: pointer;
  padding: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-left: 4px;
  border-radius: 6px;
  transition: color 0.12s, background 0.12s;
}
#popout-btn:hover { color: var(--text); background: var(--surface2); }
#popout-btn.popout-open { color: var(--accent); }
/* ── End pop-out button ── */
`;
  document.head.appendChild(style);"""

NEW_CSS_INJECT = "  // CSS moved to <style> block by sonata_popout_fix.py"

# CSS to inject into the <style> section instead (before </style> of the main block)
# We anchor on the #vol-bar-track rule which is nearby and unique
STYLE_ANCHOR = '#vol-bar-track {'
NEW_STYLE = """/* ── Pop-out button ── */
#popout-btn {
  background: none;
  border: none;
  color: var(--text3);
  cursor: pointer;
  padding: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-left: 4px;
  border-radius: 6px;
  transition: color 0.12s, background 0.12s;
}
#popout-btn:hover { color: var(--text); background: var(--surface2); }
#popout-btn.popout-open { color: var(--accent); }

#vol-bar-track {"""


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(f'Source file not found: {SOURCE}')

    html = SOURCE.read_text(encoding='utf-8')

    if IDEMPOTENCY_MARKER in html:
        print('SKIP: fix already applied. Nothing to do.')
        return

    missing = []
    for label, anchor in [
        ('old button placement', OLD_BUTTON),
        ('old CSS inject',       OLD_CSS_INJECT),
        ('style anchor',         STYLE_ANCHOR),
    ]:
        count = html.count(anchor)
        if count == 0:
            missing.append(f'{label!r} not found')
        elif count > 1:
            missing.append(f'{label!r} not unique ({count} matches)')

    if missing:
        print('ERROR:')
        for m in missing:
            print(f'  {m}')
        print('Aborting. No changes made.')
        return

    shutil.copy2(SOURCE, BACKUP)
    print(f'Backup: {BACKUP}')

    # 1. Move button inside vol-area and remove it from outside.
    html = html.replace(OLD_BUTTON, NEW_VOL_AREA_END, 1)

    # 2. Move CSS from runtime JS inject to static <style> block.
    html = html.replace(OLD_CSS_INJECT, NEW_CSS_INJECT, 1)
    html = html.replace(STYLE_ANCHOR,   NEW_STYLE, 1)

    SOURCE.write_text(html, encoding='utf-8')
    print('Done. Pop-out button moved inside vol-area, CSS made static.')
    print()
    print('Next steps:')
    print('  git add sonata-pwa.html scripts\\sonata_popout_fix.py')
    print('  git commit -m "Fix pop-out button placement and CSS"')
    print('  git push')


if __name__ == '__main__':
    main()
