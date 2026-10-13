"""
Assistant hub: the Assistant, with the Runbook as its Help view.

CONSOLIDATION (Pebble). The merged pages are unchanged files, run one at a time
by shell.hub; the switcher renders beside each page's title. Remove this file
and restore the original entries in app.py to undo the merge.
"""

from __future__ import annotations

from ais_fmd import auth
from ais_fmd.ui import shell

auth.current_user()

shell.hub(
    "assistant_hub",
    [
        ("Assistant", "Assistant.py", auth.Role.MEMBER),
        ("Help", "Runbook.py", auth.Role.MEMBER),
    ],
)
