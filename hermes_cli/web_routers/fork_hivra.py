"""Hivra (hosted Hermes) dashboard routes. FORK-ONLY module; upstream never edits it.

Mounted from ONE marked line in ``hermes_cli/web_server.py`` (``hermes-fork: hivra-web``).
Keep Hivra-specific dashboard behaviour here instead of patching upstream route modules:

* ``GET /api/hivra/config``: control-plane facts the hosted rich chat needs. Authenticated
  like every non-public ``/api/*`` route (it is NOT in ``PUBLIC_API_PATHS``).

Things the old fork patched into ``web_server.py`` that are deliberately NOT here because
config or upstream now covers them (see ``.hermesos/WEBCHAT_SEAMS.md``):

* default file-tree cwd: set ``terminal.cwd: /workspace`` in the box's config.yaml (the
  ``TERMINAL_CWD`` env alone loses to the config default ".", see the test for this module);
* chat media from ``/workspace``: the renderer reads it through ``/api/fs/read-data-url``;
* a switched provider's own ``base_url`` (e.g. Surplus): ``switch_model`` resolves it.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter

router = APIRouter()


def dashboard_url() -> Optional[str]:
    """Origin of the control-plane dashboard (``HERMES_DASHBOARD_URL``), or None when unset."""
    return (os.environ.get("HERMES_DASHBOARD_URL") or "").strip() or None


@router.get("/api/hivra/config")
async def get_hivra_config():
    """``dashboard_url`` lets the onboarding Venice card deep-link to the managed-Venice
    enable/deposit flow on the Hivra dashboard; null (local dev) makes the card fall back to
    the API-key path."""
    return {"dashboard_url": dashboard_url()}
