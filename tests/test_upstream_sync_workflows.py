"""Seam guards for the fork's upstream release sync and immutable image workflows.

hermes-fork: these files exist only in the fork (see .hermesos/FRESH_START_PLAN.md).
They encode three promises that must survive every upstream merge:

* the sync never merges its own PR and never force-pushes,
* the immutable image build never creates or moves a floating tag (:stable / :latest),
* the follow-up only trusts `upstream-sync/v*` branches from this repository.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
SYNC = WORKFLOWS / "upstream-release-sync.yml"
BUILD = WORKFLOWS / "docker-build-immutable.yml"
FOLLOWUP = WORKFLOWS / "upstream-sync-followup.yml"


def _load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    # PyYAML parses the bare key `on` as the boolean True.
    if True in data and "on" not in data:
        data["on"] = data.pop(True)
    return data


def _strip_comments(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


@pytest.mark.parametrize("path", [SYNC, BUILD, FOLLOWUP], ids=lambda p: p.name)
def test_workflow_parses_and_is_canary_only(path: Path):
    data = _load(path)
    assert data["jobs"], f"{path.name} has no jobs"
    text = path.read_text(encoding="utf-8")
    assert "ashneil12/vanilla-hermes-agent-canary" in text, (
        f"{path.name} must be guarded so it never runs on the prod fork"
    )


def test_build_never_touches_floating_tags():
    text = _strip_comments(BUILD.read_text(encoding="utf-8"))
    assert not re.search(r":(stable|latest)\b", text), "immutable build must not reference :stable/:latest"
    assert "imagetools create" not in text, "imagetools create is how floating tags get moved"
    # Every pushed tag is built from the upstream tag + sha, or the bare sha.
    pushes = re.findall(r'docker push "([^"]+)"', text)
    assert pushes, "expected explicit docker push commands"
    assert all("IMAGE_TAG" in p or "SHA" in p for p in pushes), pushes


def test_build_push_trigger_is_limited_to_proof_branches():
    triggers = _load(BUILD)["on"]
    assert triggers["push"]["branches"] == ["proof/v*"], triggers["push"]
    assert "pull_request" not in triggers


def test_build_labels_carry_revision_and_version():
    text = BUILD.read_text(encoding="utf-8")
    for label in (
        "org.opencontainers.image.revision",
        "org.opencontainers.image.version",
        "io.hermesos.upstream-tag",
    ):
        assert label in text, f"missing label {label}"
    assert "refuse to overwrite" in text.lower(), "immutability guard (no re-pointing) is gone"


def test_sync_is_scheduled_and_dispatchable_and_never_merges():
    data = _load(SYNC)
    triggers = data["on"]
    assert "schedule" in triggers and "workflow_dispatch" in triggers
    assert "push" not in triggers and "pull_request" not in triggers
    text = _strip_comments(SYNC.read_text(encoding="utf-8"))
    for forbidden in ("gh pr merge", "--auto", "git push --force", "push -f", "force-with-lease", "--admin", "reset --hard"):
        assert forbidden not in text, f"sync workflow must not use {forbidden!r}"


def test_followup_trusts_only_sync_branches_from_this_repo():
    text = FOLLOWUP.read_text(encoding="utf-8")
    assert "startsWith(github.event.workflow_run.head_branch, 'upstream-sync/v')" in text
    assert "head_repository.full_name == github.repository" in text
    assert "workflow_run.event == 'pull_request'" in text
    code = _strip_comments(text)
    for forbidden in ("gh pr merge", "--auto", "--admin"):
        assert forbidden not in code, f"follow-up must not use {forbidden!r}"
    assert "docker-build-immutable.yml" in text


def test_stuck_paths_open_or_update_an_issue():
    for path in (SYNC, FOLLOWUP):
        text = path.read_text(encoding="utf-8")
        assert "upstream-sync-stuck" in text
        assert "gh issue create" in text and ("gh issue edit" in text or "gh issue comment" in text)


def test_sync_regenerates_generated_files_and_maps_contributors():
    text = SYNC.read_text(encoding="utf-8")
    assert "scripts/ci/map_upstream_contributors.py" in text
    assert "scripts/ci/fork_runner_labels.py" in text
    assert "website/scripts/generate-skill-docs.py" in text
    # Only generated docs may be auto-resolved; real conflicts must still stop the sync.
    assert "website/sidebars" in text and "skills-catalog" in text
