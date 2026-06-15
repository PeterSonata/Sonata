#!/usr/bin/env python3
# sonata_quick_refresh.py
# ============================================================
# Adds a "Quick Refresh" button to the top level of Settings,
# alongside the skin grid. It asks Jellyfin to scan the NAS for
# newly added tracks via POST /Library/Refresh, sent through the
# existing bridge Jellyfin proxy (the bridge attaches the API
# key, so no new bridge route and no key handling in the client).
#
# This is the lightweight, everyday refresh. It is deliberately
# distinct from the existing heavy "Refresh Library" button,
# which re-fetches the whole library into the client and takes
# around 20 minutes. To stop the two being confused in the gap
# before the Advanced-settings reorganisation, this patch also
# relabels the heavy button to "Full Re-fetch".
#
# Three edits:
#   1. Insert the Quick Refresh section after the skin grid.
#   2. Insert the button's click handler before the existing
#      library-refresh-btn handler.
#   3. Relabel the heavy button "Refresh Library" -> "Full Re-fetch".
#
# Safe by design:
#   - Idempotent: exits cleanly if already applied.
#   - Loud failure: aborts without writing if any anchor is
#     missing or not unique, so a moved anchor can never produce
#     a half-applied file.
#   - Timestamped backup before any write.
#
# Run from the repo root (where sonata-pwa.html lives):
#   python scripts\sonata_quick_refresh.py
# ============================================================

import sys
import shutil
import datetime
from pathlib import Path

SRC = Path("sonata-pwa.html")

# ── Anchors (file is CRLF on disk; read_text normalises to LF, so match \n) ──
ANCHOR_HTML = '    <div id="skin-grid"></div>\n'
ANCHOR_JS   = "document.getElementById('library-refresh-btn').onclick = () => {"
ANCHOR_LABEL = "        Refresh Library\n"

# ── Injected Settings markup (sits right after the skin grid) ────────────────
NEW_HTML = (
    '    <div class="settings-section-label" style="margin-top:0;border-top:var(--bw) solid var(--border)">Quick refresh</div>\n'
    '    <div style="padding:16px 20px;border-bottom:var(--bw) solid var(--border)">\n'
    '      <button id="quick-refresh-btn"\n'
    "        style=\"background:var(--surface2);border:var(--bw) solid var(--border);color:var(--text);padding:10px 16px;font-family:'IBM Plex Sans',sans-serif;font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;cursor:pointer;width:100%;\">\n"
    "        Quick Refresh\n"
    "      </button>\n"
    "      <div id=\"quick-refresh-status\" style=\"font-size:11px;font-family:'IBM Plex Mono',monospace;color:var(--text3);letter-spacing:0.06em;line-height:1.55;margin-top:10px\">Asks Jellyfin to scan the NAS for newly added tracks. Runs in the background and starts instantly.</div>\n"
    "    </div>\n"
)

# ── Injected click handler (goes before the heavy refresh handler) ───────────
NEW_JS = (
    "document.getElementById('quick-refresh-btn').onclick = async () => {\n"
    "  const btn = document.getElementById('quick-refresh-btn');\n"
    "  const status = document.getElementById('quick-refresh-status');\n"
    "  if (!jellyfin.serverUrl) {\n"
    "    if (status) status.textContent = 'Connect to the bridge first (see Connection below).';\n"
    "    return;\n"
    "  }\n"
    "  const orig = btn.textContent;\n"
    "  btn.disabled = true;\n"
    "  btn.textContent = 'Requesting\u2026';\n"
    "  try {\n"
    "    // POST /jellyfin/Library/Refresh through the bridge proxy; the bridge\n"
    "    // attaches the Jellyfin API key. Returns immediately, scan runs server-side.\n"
    "    await jfPost('/Library/Refresh', {});\n"
    "    if (status) status.textContent = 'Scan started. Jellyfin is indexing the NAS in the background; new tracks appear once it finishes.';\n"
    "  } catch (e) {\n"
    "    if (status) status.textContent = 'Could not start scan: ' + e.message;\n"
    "  } finally {\n"
    "    btn.textContent = orig;\n"
    "    btn.disabled = false;\n"
    "  }\n"
    "};\n\n"
)


def die(msg):
    print(f"\n  ABORTED: {msg}\n  No changes written.")
    sys.exit(1)


def main():
    if not SRC.exists():
        die(f"{SRC} not found. Run this from the repo root.")

    text = SRC.read_text(encoding="utf-8")

    # Idempotency
    if "quick-refresh-btn" in text:
        print("  Already applied (quick-refresh-btn present). Nothing to do.")
        return

    # Verify every anchor is present exactly once before touching anything
    for name, anchor in (("skin-grid", ANCHOR_HTML), ("refresh handler", ANCHOR_JS), ("button label", ANCHOR_LABEL)):
        count = text.count(anchor)
        if count != 1:
            die(f"anchor '{name}' found {count} times, expected 1. Source may have moved on.")

    # Backup
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = SRC.with_name(f"sonata-pwa.backup-{stamp}.html")
    shutil.copy2(SRC, backup)

    # Apply
    text = text.replace(ANCHOR_HTML, ANCHOR_HTML + NEW_HTML, 1)
    text = text.replace(ANCHOR_JS, NEW_JS + ANCHOR_JS, 1)
    text = text.replace(ANCHOR_LABEL, "        Full Re-fetch\n", 1)

    SRC.write_text(text, encoding="utf-8")

    print("  Quick Refresh patch applied.")
    print(f"  Backup: {backup.name}")
    print("  Edits: added Quick refresh section + handler, relabelled heavy button to 'Full Re-fetch'.")


if __name__ == "__main__":
    main()
