"""hermes-fork: scripts/ci/map_upstream_contributors.py keeps the contributor gate green on syncs."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "map_upstream_contributors.py"


def _load():
    spec = importlib.util.spec_from_file_location("map_upstream_contributors", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(repo: Path, email: str, name: str, fname: str) -> None:
    (repo / fname).write_text(fname)
    _git(repo, "add", fname)
    _git(repo, "-c", f"user.email={email}", "-c", f"user.name={name}", "commit", "-q", "-m", fname)


def test_exempt_and_mapped_rules():
    mod = _load()
    assert mod.is_exempt("12345+someone@users.noreply.github.com")
    assert mod.is_exempt("github-actions[bot]@users.noreply.github.com")
    assert not mod.is_exempt("stranger@example.com")
    assert mod.is_mapped("a@b.c", '    "a@b.c": "x",')
    assert not mod.is_mapped("zz-no-such@example.com", "")


def test_maps_unmapped_authors_with_placeholder(tmp_path, monkeypatch):
    mod = _load()
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "scripts").mkdir()
    (repo / "scripts" / "release.py").write_text('MAP = {"legacy@example.com": "legacy"}\n')
    _git(repo, "add", "-A")
    _commit(repo, "base@example.com", "Base", "base.txt")
    _git(repo, "branch", "origin-main")
    _commit(repo, "stranger@example.com", "Stranger", "a.txt")
    _commit(repo, "legacy@example.com", "Legacy", "b.txt")
    _commit(repo, "bare@users.noreply.github.com", "Bare", "c.txt")
    _commit(repo, "99+exempt@users.noreply.github.com", "Exempt", "d.txt")

    monkeypatch.setattr(mod, "REPO_ROOT", repo)
    monkeypatch.setattr(mod, "EMAILS_DIR", repo / "contributors" / "emails")
    monkeypatch.setattr(mod, "lookup_login", lambda e: mod.BARE_NOREPLY_RE.match(e).group(1) if mod.BARE_NOREPLY_RE.match(e) else None)
    monkeypatch.setattr("sys.argv", ["x", "--base", "origin-main"])
    assert mod.main() == 0

    emails = repo / "contributors" / "emails"
    assert (emails / "stranger@example.com").read_text().startswith(mod.PLACEHOLDER)
    assert (emails / "bare@users.noreply.github.com").read_text().startswith("bare")
    assert not (emails / "legacy@example.com").exists(), "already in legacy AUTHOR_MAP"
    assert not (emails / "99+exempt@users.noreply.github.com").exists(), "id+login noreply is auto-resolved by CI"
