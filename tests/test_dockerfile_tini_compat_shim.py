"""Regression test for #34192 — Dockerfile must keep the tini compat shim
for orchestration templates that still reference /usr/bin/tini.

This is a documentation-as-test guard: removing the shim is a real
choice, but it should be done deliberately (e.g. once Hostinger's
'Hermes WebUI' catalog updates to /init) and not by accident.

2026-07-22 sync note (hermes-fork): upstream #66679 superseded the plain
``ln -sf /init /usr/bin/tini`` symlink with ``docker/tini-shim.sh`` — the
symlink forwarded tini flags like ``-g`` into s6-overlay's rc.init as the
container CMD and boot-looped ``restart: unless-stopped`` deploys. The
guarded INTENT is unchanged: /usr/bin/tini must exist for legacy external
wrappers; these asserts now pin the shim mechanism instead.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def _dockerfile_text() -> str:
    return (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_tini_compat_shim_present():
    """/usr/bin/tini must exist in the image for #34192 (now via the
    flag-stripping shim from upstream #66679, not a bare symlink)."""
    df = _dockerfile_text()
    assert "COPY --chmod=0755 docker/tini-shim.sh /usr/bin/tini" in df, (
        "Dockerfile must keep the tini compat shim at /usr/bin/tini "
        "(#34192 / #66679). Removing it breaks orchestration templates "
        "that still pin /usr/bin/tini as the entrypoint (Hostinger "
        "'Hermes WebUI' catalog as of v0.14.x)."
    )


def test_tini_shim_script_execs_init():
    """The shim script must exist and hand off to /init — it exists only
    to strip the tini CLI surface before delegating to s6-overlay."""
    shim = REPO_ROOT / "docker" / "tini-shim.sh"
    assert shim.is_file(), (
        "docker/tini-shim.sh is COPY'd to /usr/bin/tini by the Dockerfile "
        "(#34192 / #66679) and must exist in the build context."
    )
    text = shim.read_text(encoding="utf-8")
    assert "/init" in text, (
        "docker/tini-shim.sh must delegate to /init (s6-overlay) after "
        "stripping tini flags — otherwise legacy /usr/bin/tini wrappers "
        "lose process supervision."
    )


def test_tini_compat_comment_explains_why():
    """The shim line is comment-anchored to #34192 so a future reader
    knows why it exists. Removing the comment makes it look like dead
    code worth deleting."""
    df = _dockerfile_text()
    assert "#34192" in df, (
        "The Dockerfile tini compat shim must keep its #34192 anchor "
        "comment so future maintainers know why the shim is there."
    )


def test_entrypoint_still_init_not_tini():
    """Sanity check: the actual ENTRYPOINT is still /init (s6-overlay).
    The shim is for legacy external wrappers, not for the image's own
    runtime — that path must continue to use the canonical /init."""
    df = _dockerfile_text()
    assert 'ENTRYPOINT [ "/init"' in df, (
        "Dockerfile ENTRYPOINT must remain /init (s6-overlay). The "
        "tini shim is only for external wrappers that haven't been "
        "updated yet."
    )
