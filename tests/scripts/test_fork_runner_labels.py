"""hermes-fork: scripts/ci/fork_runner_labels.py keeps upstream CI runnable on standard runners."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "fork_runner_labels.py"
spec = importlib.util.spec_from_file_location("fork_runner_labels", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

SAMPLE = """name: t
jobs:
  big:
    runs-on: ubuntu-latest-96-core
    timeout-minutes: 30
    steps:
      - run: echo hi
  small:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - run: echo hi
  arm:
    runs-on: ${{ matrix.runner }}
    timeout-minutes: 20
    strategy:
      matrix:
        include:
          - runner: ubuntu-latest-32-arm-core
          - runner: windows-latest-32-core
          - runner: macos-latest
    steps:
      - run: echo hi
"""


def test_rewrites_large_runner_jobs_and_scales_only_their_timeouts():
    out = mod.rewrite(SAMPLE)
    assert "ubuntu-latest-96-core" not in out and "-core" not in out
    assert "runs-on: ubuntu-latest\n    timeout-minutes: 120" in out  # 30 * 4
    assert "runs-on: ubuntu-latest\n    timeout-minutes: 10\n" in out  # untouched job
    assert "runner: ubuntu-24.04-arm" in out and "runner: windows-latest" in out
    assert "runner: macos-latest" in out


def test_idempotent():
    once = mod.rewrite(SAMPLE)
    assert mod.rewrite(once) == once


def test_timeout_is_capped():
    out = mod.rewrite("jobs:\n  x:\n    runs-on: ubuntu-latest-32-core\n    timeout-minutes: 200\n")
    assert "timeout-minutes: 360" in out


def test_repo_workflows_use_no_larger_runners():
    """Fails right after a plain upstream merge; the sync workflow runs the script before pushing."""
    workflows = Path(__file__).resolve().parents[2] / ".github" / "workflows"
    offenders = [
        p.name for p in sorted(workflows.glob("*.y*ml")) if mod.LARGE_RE.search(p.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"run scripts/ci/fork_runner_labels.py: {offenders}"
