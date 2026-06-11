"""
Smoke tests for the aeon default skill.

We can't exercise the GitHub Actions round-trip in CI (needs a PAT + network),
so these tests verify:
  - SKILL.md frontmatter conforms to the hardline format
  - the hermes.config block is the required list-of-{key,description} shape
  - shipped bash scripts parse cleanly (bash -n)
  - _lib.sh loads credentials from a config.yaml (skills.config.*) correctly
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

SKILL_DIR = Path(__file__).resolve().parents[2] / "skills" / "autonomous-ai-agents" / "aeon"
SCRIPTS = ["_lib.sh", "aeon-setup.sh", "aeon-list-skills.sh", "aeon-invoke.sh", "aeon-enable-skill.sh", "aeon-check-outputs.sh"]


@pytest.fixture(scope="module")
def frontmatter() -> dict:
    src = (SKILL_DIR / "SKILL.md").read_text()
    m = re.search(r"^---\n(.*?)\n---", src, re.DOTALL)
    assert m, "SKILL.md missing YAML frontmatter"
    return yaml.safe_load(m.group(1))


def test_skill_dir_exists() -> None:
    assert SKILL_DIR.is_dir(), f"missing skill dir: {SKILL_DIR}"


def test_skill_md_present() -> None:
    assert (SKILL_DIR / "SKILL.md").is_file()


def test_description_under_60_chars(frontmatter) -> None:
    desc = frontmatter["description"]
    assert len(desc) <= 60, f"description is {len(desc)} chars (hardline <=60): {desc!r}"


def test_config_block_is_list_of_key_description(frontmatter) -> None:
    """The loader (agent/skill_utils.py extract_skill_config_vars) silently drops
    any config entry lacking 'key'/'description', so this shape is load-bearing."""
    cfg = frontmatter["metadata"]["hermes"]["config"]
    assert isinstance(cfg, list), "hermes.config must be a LIST, not a map"
    keys = set()
    for entry in cfg:
        assert isinstance(entry, dict), f"config entry not a dict: {entry!r}"
        assert entry.get("key"), f"config entry missing 'key': {entry!r}"
        assert entry.get("description"), f"config entry missing 'description': {entry!r}"
        keys.add(entry["key"])
    # Token-only model: only the PAT is user-provided. The fork repo is
    # auto-discovered/created and recorded by the skill, not prompted here.
    assert "aeon_github_pat" in keys, f"expected aeon_github_pat, got {keys}"


def test_scripts_present_and_executable() -> None:
    for name in SCRIPTS:
        p = SKILL_DIR / "scripts" / name
        assert p.is_file(), f"missing script: {name}"
    # operation scripts (not the sourced lib) should be executable
    for name in SCRIPTS:
        if name == "_lib.sh":
            continue
        assert (SKILL_DIR / "scripts" / name).stat().st_mode & 0o111, f"{name} not executable"


@pytest.mark.skipif(not shutil.which("bash"), reason="bash not available")
def test_scripts_bash_syntax() -> None:
    for name in SCRIPTS:
        p = SKILL_DIR / "scripts" / name
        r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
        assert r.returncode == 0, f"bash syntax error in {name}: {r.stderr}"


@pytest.mark.skipif(not shutil.which("bash"), reason="bash not available")
def test_lib_loads_config_from_yaml(tmp_path) -> None:
    """_lib.sh should read skills.config.aeon_* out of HERMES_HOME/config.yaml."""
    home = tmp_path / "hermes_home"
    home.mkdir()
    (home / "config.yaml").write_text(
        "skills:\n"
        "  config:\n"
        "    aeon_github_pat: ghp_testtoken123\n"
        "    aeon_fork_repo: someone/aeon\n"
    )
    lib = SKILL_DIR / "scripts" / "_lib.sh"
    script = f'set -euo pipefail; source "{lib}"; _aeon_load_config; echo "$AEON_PAT|$AEON_FORK_REPO"'
    r = subprocess.run(
        ["bash", "-c", script],
        capture_output=True, text=True, env={"HERMES_HOME": str(home), "PATH": __import__("os").environ["PATH"]},
    )
    assert r.returncode == 0, f"_lib.sh failed: {r.stderr}"
    assert r.stdout.strip() == "ghp_testtoken123|someone/aeon", r.stdout


@pytest.mark.skipif(not shutil.which("bash"), reason="bash not available")
def test_lib_reports_unconfigured(tmp_path) -> None:
    """With no config.yaml, _lib.sh exits non-zero and tells the user where to set it."""
    home = tmp_path / "empty_home"
    home.mkdir()
    lib = SKILL_DIR / "scripts" / "_lib.sh"
    script = f'source "{lib}"; _aeon_load_config'
    r = subprocess.run(
        ["bash", "-c", script],
        capture_output=True, text=True, env={"HERMES_HOME": str(home), "PATH": __import__("os").environ["PATH"]},
    )
    assert r.returncode != 0
    assert "not configured" in r.stderr.lower()
