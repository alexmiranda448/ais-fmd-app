"""
Settings hub: the Audit Log, with Officer Access waiting beside it.

CONSOLIDATION (Pebble). The merged pages are unchanged files, run one at a time
by shell.hub; the switcher renders beside each page's title. Remove this file
and restore the original entries in app.py to undo the merge.

MVP SCOPE. Officer Access stays deferred for the first production term (see
app.py): its `profiles` table lives in migration 002, which is not run. With
one view left the hub shows no switcher. Uncomment the line to turn it back on.
"""

from __future__ import annotations

from ais_fmd import auth
from ais_fmd.ui import shell

auth.current_user()

shell.hub(
    "settings_hub",
    [
        # ("Officer Access", "OfficerAccess.py", auth.Role.TREASURER),  # MVP: deferred
        ("Audit Log", "AuditLog.py", auth.Role.TREASURER),
    ],
)
