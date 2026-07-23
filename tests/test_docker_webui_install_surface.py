"""Guards for the multi-container Hermes WebUI install surface.

2026-07-22 sync note (hermes-fork): the read-only-source build/egg_info
temp-output redirect test was removed with its subject — upstream #68217
rewrote setup.py into a wheel/sdist build guard (pip/PyPI installs are no
longer supported, so nothing pip-installs the read-only /opt/hermes tree;
the Docker image installs editable at build time on a writable tree). The
LICENSE .dockerignore guard below is still live.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_docker_context_includes_license_file() -> None:
    """PEP 639 license-files metadata must resolve inside the Docker image."""
    dockerignore = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")
    active_lines = [
        line.strip()
        for line in dockerignore.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert "LICENSE" not in active_lines
