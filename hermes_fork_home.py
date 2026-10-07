"""Hivra fork: read-only install-tree HERMES_HOME guard (fork-only, stdlib-only leaf module).

The Docker image bakes its code tree at ``/opt/hermes`` as a read-only, root-owned mount. It is
NEVER a valid Hermes home: anything written under it (chat uploads, auth.json, config.yaml,
sessions) fails with ``[Errno 13] Permission denied: '/opt/hermes'``. Two ways a managed box ends
up pointing there, both seen on webfree boxes:

1. ``HERMES_HOME`` is lost (a stale entrypoint leaves ``HOME=/opt/hermes``), so the platform
   default resolves to ``/opt/hermes/.hermes``. -> :func:`install` wraps the home resolvers so a
   result inside the install tree is redirected to a writable, agent-shared data home.
2. A stale persisted ``.env`` that still carries ``HERMES_HOME=`` / ``HOME=`` lines clobbers the
   container-injected values through ``load_dotenv(override=True)``. -> :func:`pin_infra_env`
   wraps ``load_hermes_dotenv`` so the live environment wins over the file.

Wiring (the only upstream edits, seam ``install-dir-home-guard``): one hook line at the bottom of
``hermes_constants.py`` and one at the bottom of ``hermes_cli/env_loader.py``.
"""

from __future__ import annotations

import functools
import os
import sys
from pathlib import Path
from typing import Any, Callable, MutableMapping

# The Docker image's read-only install tree: never a valid Hermes home.
_DOCKER_INSTALL_DIR = Path("/opt/hermes")
# Preference order; an operator can prepend one via HERMES_WRITE_SAFE_ROOT. The webfree split
# deploy mounts the uid-1024 webui-state at /home/hermes/.hermes (shared with the gateway that later
# reads attachments); the single-container deploy uses the /opt/data volume. Never hardcode one:
# /opt/data is owned by uid 10000 and is NOT writable from the uid-1024 dashboard container.
_DOCKER_DATA_HOME_CANDIDATES = (Path("/home/hermes/.hermes"), Path("/opt/data"))
_install_dir_home_warned: bool = False

# Resolvers wrapped by install(); every return is passed through redirect_install_dir_home().
_GUARDED_RESOLVERS = ("get_hermes_home", "get_process_hermes_home", "get_default_hermes_root")


def _writable_data_home() -> Path | None:
    """First existing, current-uid-writable data-home candidate, or None."""
    candidates: list[Path] = []
    override = os.environ.get("HERMES_WRITE_SAFE_ROOT", "").strip()
    if override:
        candidates.append(Path(override))
    candidates.extend(_DOCKER_DATA_HOME_CANDIDATES)
    for cand in candidates:
        try:
            if cand.is_dir() and os.access(cand, os.W_OK):
                return cand
        except OSError:
            continue
    return None


def redirect_install_dir_home(home: Path) -> Path:
    """Redirect a Hermes home that landed inside the read-only install tree.

    Returns ``home`` unchanged on every normal path (home outside the install tree) with no
    filesystem probe. Only when ``home`` is inside the read-only tree do we probe for a writable
    target; if NONE is writable by the current uid we return ``home`` unchanged so the failure
    stays VISIBLE rather than silently relocating to another unwritable path.
    """
    try:
        in_install_tree = home == _DOCKER_INSTALL_DIR or _DOCKER_INSTALL_DIR in home.parents
    except (OSError, ValueError, AttributeError):
        return home
    if not in_install_tree:
        return home
    target = _writable_data_home()
    if target is None:
        return home

    global _install_dir_home_warned
    if not _install_dir_home_warned:
        _install_dir_home_warned = True
        # Direct stderr (not logging): this runs at import time, before logging is configured.
        msg = (
            f"[HERMES_HOME guard] Resolved Hermes home {str(home)!r} is inside "
            f"the read-only install tree {str(_DOCKER_INSTALL_DIR)!r} — writes "
            f"there fail with EACCES. HERMES_HOME was lost before this process "
            f"started; falling back to {str(target)!r}. Set HERMES_HOME "
            f"explicitly to silence this."
        )
        try:
            sys.stderr.write(msg + "\n")
            sys.stderr.flush()
        except Exception:
            pass
    return target


def _guarded(fn: Callable[..., Path]) -> Callable[..., Path]:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Path:
        return redirect_install_dir_home(fn(*args, **kwargs))

    wrapper.__hermes_fork_guarded__ = True  # type: ignore[attr-defined]
    return wrapper


def install(namespace: MutableMapping[str, Any]) -> None:
    """Wrap the home resolvers in ``hermes_constants``' namespace (idempotent)."""
    for name in _GUARDED_RESOLVERS:
        fn = namespace.get(name)
        if fn is not None and not getattr(fn, "__hermes_fork_guarded__", False):
            namespace[name] = _guarded(fn)


def pin_infra_env(load_fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``load_hermes_dotenv`` so ``HERMES_HOME`` / ``HOME`` set before the load stay authoritative.

    Profile switching sets ``HERMES_HOME`` through the environment or a context override, never
    through ``.env``, so this never fights a legitimate value. Only already-set values are pinned:
    an unset ``HERMES_HOME`` still loads from the file (the resolver guard backstops a bad value).
    """
    if getattr(load_fn, "__hermes_fork_guarded__", False):
        return load_fn

    @functools.wraps(load_fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        pinned = {k: os.environ[k] for k in ("HERMES_HOME", "HOME") if os.environ.get(k)}
        try:
            return load_fn(*args, **kwargs)
        finally:
            for key, value in pinned.items():
                os.environ[key] = value

    wrapper.__hermes_fork_guarded__ = True  # type: ignore[attr-defined]
    return wrapper
