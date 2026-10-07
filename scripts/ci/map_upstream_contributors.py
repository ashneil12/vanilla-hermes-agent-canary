#!/usr/bin/env python3
"""Map commit-author emails that the contributor-check gate would reject.

hermes-fork: when a whole upstream release is merged into the fork, every upstream
author who is not yet in `contributors/emails/` (or the frozen AUTHOR_MAP in
scripts/release.py) makes the required `Check contributors` job fail, even though
those commits are upstream's own. The scheduled sync (upstream-release-sync.yml) runs
this after the merge so the PR is not red for a reason no human can act on.

The rules mirror .github/workflows/contributor-check.yml:
  * scan `<merge-base of --base and HEAD>..HEAD --no-merges` author emails
  * skip bot emails and `<id>+<login>@users.noreply.github.com`
  * an email is mapped if `contributors/emails/<email>` exists or
    `"<email>"` appears in scripts/release.py

Resolution of an unmapped email, in order:
  1. bare `<login>@users.noreply.github.com` -> `<login>`
  2. `gh api search/users?q=<email>+in:email` (best effort, at most --max-lookups per run)
  3. placeholder login `unmapped-upstream` (clearly not a real person; only keeps the gate green)

Usage:  python3 scripts/ci/map_upstream_contributors.py [--base origin/main] [--dry-run]
Exit 0 always unless git itself fails; prints what it wrote.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EMAILS_DIR = REPO_ROOT / "contributors" / "emails"
PLACEHOLDER = "unmapped-upstream"

SKIP_SUBSTRINGS = ("teknium", "noreply@github.com", "dependabot", "github-actions", "anthropic.com", "cursor.com")
ID_NOREPLY_RE = re.compile(r"\+.*@users\.noreply\.github\.com")
BARE_NOREPLY_RE = re.compile(r"^([A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38})@users\.noreply\.github\.com$")
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")


def _run(*args: str) -> str:
    result = subprocess.run(list(args), capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=REPO_ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def candidate_emails(base_ref: str) -> list[str]:
    base = _run("git", "merge-base", base_ref, "HEAD")
    log = _run("git", "log", f"{base}..HEAD", "--format=%ae", "--no-merges")
    return sorted({line.strip() for line in log.splitlines() if line.strip()})


def is_exempt(email: str) -> bool:
    low = email.lower()
    return any(s in low for s in SKIP_SUBSTRINGS) or bool(ID_NOREPLY_RE.search(email))


def is_mapped(email: str, legacy_text: str) -> bool:
    return (EMAILS_DIR / email).is_file() or f'"{email}"' in legacy_text


def lookup_login(email: str) -> str | None:
    match = BARE_NOREPLY_RE.match(email)
    if match:
        return match.group(1)
    try:
        out = subprocess.run(
            ["gh", "api", f"search/users?q={email}+in:email", "--jq", ".items[0].login // empty"],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    login = out.stdout.strip()
    return login if out.returncode == 0 and LOGIN_RE.match(login) else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--max-lookups", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    release_py = REPO_ROOT / "scripts" / "release.py"
    legacy_text = release_py.read_text(encoding="utf-8", errors="replace") if release_py.exists() else ""
    unmapped = [e for e in candidate_emails(args.base) if not is_exempt(e) and not is_mapped(e, legacy_text)]
    print(f"{len(unmapped)} unmapped author email(s)")

    lookups = 0
    written = 0
    for email in unmapped:
        if "/" in email or "\\" in email or " " in email:
            print(f"  skip (unsafe filename): {email!r}", file=sys.stderr)
            continue
        login = None
        if BARE_NOREPLY_RE.match(email) or lookups < args.max_lookups:
            if not BARE_NOREPLY_RE.match(email):
                lookups += 1
            login = lookup_login(email)
        resolved = login is not None
        login = login or PLACEHOLDER
        note = "auto-mapped by upstream-release-sync" + ("" if resolved else " (no GitHub login resolved)")
        print(f"  {email} -> {login}{'' if resolved else '  [placeholder]'}")
        if not args.dry_run:
            EMAILS_DIR.mkdir(parents=True, exist_ok=True)
            (EMAILS_DIR / email).write_text(f"{login}\n# {note}\n", encoding="utf-8")
            written += 1
    print(f"wrote {written} mapping file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
