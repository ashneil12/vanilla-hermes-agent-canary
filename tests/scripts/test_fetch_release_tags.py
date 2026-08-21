from __future__ import annotations

import subprocess
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "sandbox" / "fetch-release-tags.sh"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_fetch_release_tags_imports_authoritative_remote_tags(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init")
    _git(source, "config", "user.name", "Test")
    _git(source, "config", "user.email", "test@example.com")
    (source / "README.md").write_text("release\n", encoding="utf-8")
    _git(source, "add", "README.md")
    _git(source, "commit", "-m", "release")
    _git(source, "tag", "v2026.8.19")
    _git(source, "tag", "backup/not-a-release")

    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _git(consumer, "init")

    result = subprocess.run(
        [str(SCRIPT), "--repo", str(consumer), "--remote", str(source)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _git(consumer, "tag", "--list", "v2026.*").stdout.splitlines() == [
        "v2026.8.19"
    ]
    assert _git(consumer, "tag", "--list", "backup/*").stdout == ""
    assert "Imported 1 release tag(s)" in result.stdout
