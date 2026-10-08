"""Regression guards for commit-accurate published Docker images."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _workflow_step(workflow: str, name: str) -> str:
    marker = f"      - name: {name}\n"
    start = workflow.index(marker)
    end = workflow.find("\n      - name:", start + len(marker))
    return workflow[start:] if end == -1 else workflow[start:end]


def test_publisher_keys_smoke_and_immutable_builds_by_commit_sha() -> None:
    """Every cached publisher build receives the source commit it packages."""
    workflow = (REPO_ROOT / ".github/workflows/docker-publish.yml").read_text(
        encoding="utf-8"
    )

    for step_name in (
        "Build image (amd64, smoke test)",
        "Push amd64 image with SHA tag (main branch)",
        "Push multi-arch image (release)",
    ):
        step = _workflow_step(workflow, step_name)
        assert "build-args: |" in step
        assert "HERMES_GIT_SHA=${{ github.sha }}" in step


def test_editable_install_is_commit_keyed_and_clears_stale_metadata() -> None:
    """A reused dependency cache must not retain an older Hermes version.

    hermes-fork: editable-install-revision-key. The fork keeps upstream's install line
    untouched and adds its own marked RUN (with the revision ARG) directly before it.
    """
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    marker = "# hermes-fork: editable-install-revision-key"
    install = 'RUN uv pip install --no-cache-dir --no-deps -e "."'
    assert marker in dockerfile, "fork seam marker is gone"
    start = dockerfile.index(marker)
    end = dockerfile.index(install)
    assert start < end, "the revision-key RUN must come before the editable install"
    block = dockerfile[start:end]

    assert "ARG HERMES_GIT_SHA=" in block
    assert "${HERMES_GIT_SHA" in block
    assert "rm -rf" in block
    assert "hermes_agent-*.dist-info" in block
    assert "__editable__.hermes_agent-*.pth" in block
    assert "hermes_agent*.egg-info" in block


def test_publisher_blocks_images_with_stale_package_metadata() -> None:
    """The smoke image must prove its installed version matches pyproject."""
    workflow = (REPO_ROOT / ".github/workflows/docker-publish.yml").read_text(
        encoding="utf-8"
    )
    step = _workflow_step(workflow, "Test packaged Hermes version")

    assert 'version("hermes-agent")' in step
    assert 'open("/opt/hermes/pyproject.toml", "rb")' in step
    assert "Hermes package metadata mismatch" in step
