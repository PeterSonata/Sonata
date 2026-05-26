"""
sonata_bridge_user_force.py
===========================
Follow-up to sonata_bridge_user.py. Removes the short-circuit that
prevents re-resolution when a cached userId is already in localStorage.

Without this, devices that connected to Jellyfin before the
sonata-bridge user existed are stuck on the old (personal) user's
GUID, because resolveJellyfinUser() exits early when jellyfin.userId
is set from localStorage at page load.

With this patch, the function always queries /Users and re-picks the
sonata-bridge user, making the fix self-applying on next load with no
manual cache clears.

Usage (from repo root):
  python scripts\\sonata_bridge_user_force.py
"""

from pathlib import Path
from datetime import datetime
import sys

SOURCE = Path('sonata-pwa.html')

if not SOURCE.exists():
    print(f"ERROR: {SOURCE} not found. Run from the repo root.")
    sys.exit(1)

text = SOURCE.read_text(encoding='utf-8')

OLD = (
    "async function resolveJellyfinUser() {\n"
    "  if (jellyfin.userId) return true;\n"
    "  const data = await jfGet('/Users');\n"
)

NEW = (
    "async function resolveJellyfinUser() {\n"
    "  // Always re-query to catch stale cached userIds (e.g. when the\n"
    "  // sonata-bridge user is added after a device first connected)\n"
    "  const data = await jfGet('/Users');\n"
)

if OLD not in text:
    if NEW in text:
        print("Patch already applied. Nothing to do.")
        sys.exit(0)
    print("ERROR: anchor not found. Source may have changed.")
    sys.exit(1)

stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
backup = SOURCE.with_suffix(f'.backup-{stamp}.html')
backup.write_text(text, encoding='utf-8')
print(f"Backed up to {backup.name}")

patched = text.replace(OLD, NEW, 1)
SOURCE.write_text(patched, encoding='utf-8')
print("Removed userId short-circuit in resolveJellyfinUser().")