"""
sonata_bridge_user.py
=====================
Patches resolveJellyfinUser() to prefer a Jellyfin user named
'sonata-bridge' over data[0] when resolving the userId from /Users.

Without this patch, Sonata caches whichever user Jellyfin returns
first, tying its library visibility to that user. Revoking library
access from that user (e.g. to hide tiles on the Jellyfin home
screen) then breaks Sonata.

With this patch, Sonata looks for a 'sonata-bridge' user and uses
its GUID. Falls back to data[0] if no such user exists, so the patch
is safe to apply before the bridge user is created.

Usage (from repo root):
  python scripts\\sonata_bridge_user.py
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
    "  if (!data || !data.length) throw new Error('No users found');\n"
    "  jellyfin.userId = data[0].Id;\n"
)

NEW = (
    "  if (!data || !data.length) throw new Error('No users found');\n"
    "  // Prefer the dedicated sonata-bridge user; fall back to first user\n"
    "  const bridgeUser = data.find(u => u.Name === 'sonata-bridge');\n"
    "  jellyfin.userId = bridgeUser ? bridgeUser.Id : data[0].Id;\n"
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
print("Patched resolveJellyfinUser() to prefer 'sonata-bridge' user.")