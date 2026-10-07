"""hermes-fork: held-lock-keeps-identity-files.

``gateway.status._cleanup_invalid_pid_path`` unlinks ``gateway.pid`` / ``gateway.lock`` whenever
``get_running_pid()`` cannot verify the recorded gateway locally. On Hivra's split-container boxes the
gateway holds the runtime lock from another PID namespace, so a status poll from the dashboard
container would delete a live gateway's identity files, and a second gateway could then lock a fresh
inode (double-run).

For the process's own home (an unscoped query) the lock, not local PID visibility, is the liveness
proof: never cleanup-unlink while it is held. Scoped queries of another profile home and the
lock-inactive path keep upstream's behaviour. Add-only module; ``gateway/status.py`` carries one
decorator line.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Callable

GUARDED_ATTR = "__hermes_fork_held_lock_guard__"


def keep_held_lock_files(fn: Callable) -> Callable:
    @functools.wraps(fn)
    def wrapper(pid_path, *args, **kwargs):
        from gateway import status

        try:
            if Path(pid_path) == Path(status._get_pid_path()) and status.is_gateway_runtime_lock_active(
                status._get_gateway_lock_path(Path(pid_path))
            ):
                return None
        except Exception:
            pass  # probe failure keeps upstream behaviour
        return fn(pid_path, *args, **kwargs)

    setattr(wrapper, GUARDED_ATTR, True)
    return wrapper
