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
    """A reused dependency cache must not retain an older Hermes version."""
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    install_marker = 'uv pip install --no-cache-dir --no-deps -e "."'
    install_end = dockerfile.index(install_marker) + len(install_marker)
    install_start = dockerfile.rfind("RUN ", 0, install_end)
    install_block = dockerfile[install_start:install_end]

    assert dockerfile.index("ARG HERMES_GIT_SHA=") < install_start
    assert "${HERMES_GIT_SHA" in install_block
    assert "rm -rf" in install_block
    assert "hermes_agent-*.dist-info" in install_block
    assert "__editable__.hermes_agent-*.pth" in install_block
    assert "hermes_agent*.egg-info" in install_block


def test_publisher_blocks_images_with_stale_package_metadata() -> None:
    """The smoke image must prove its installed version matches pyproject."""
    workflow = (REPO_ROOT / ".github/workflows/docker-publish.yml").read_text(
        encoding="utf-8"
    )
    step = _workflow_step(workflow, "Test packaged Hermes version")

    assert 'version("hermes-agent")' in step
    assert 'open("/opt/hermes/pyproject.toml", "rb")' in step
    assert "Hermes package metadata mismatch" in step
