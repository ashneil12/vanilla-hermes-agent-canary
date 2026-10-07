#!/usr/bin/env python3
"""Run upstream's workflows on GitHub-hosted standard runners.

hermes-fork: since upstream 2026-09 the test, JS, Rust and e2e jobs use Nous's larger
runners (`ubuntu-latest-96-core`, `ubuntu-latest-32-core`, `ubuntu-latest-32-arm-core`,
`windows-latest-32-core`). A personal account has none, so those jobs sit in `queued`
forever and the required check `All required checks pass` can never go green.

This rewrites the labels to standard runners and scales `timeout-minutes` for every job
that used a larger runner (the suite is sized for 32 to 96 cores, a standard runner has 4).
It is idempotent and text-based, so it can run after every upstream merge
(upstream-release-sync.yml does that) and the diff stays a handful of `runs-on` and
`timeout-minutes` lines.

Usage: python3 scripts/ci/fork_runner_labels.py [--check] [paths...]
  --check   exit 1 if any file would change (used by tests); writes nothing
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

# Longest first so `-32-arm-core` is not eaten by the generic pattern.
LABEL_RULES = (
    (re.compile(r"ubuntu-latest-\d+-arm-core"), "ubuntu-24.04-arm"),
    (re.compile(r"ubuntu-latest-\d+-core"), "ubuntu-latest"),
    (re.compile(r"windows-latest-\d+-core"), "windows-latest"),
)
LARGE_RE = re.compile("|".join(r.pattern for r, _ in LABEL_RULES))
JOB_KEY_RE = re.compile(r"^  [A-Za-z0-9_-]+:\s*(#.*)?$")
TIMEOUT_RE = re.compile(r"^(\s+timeout-minutes:\s*)(\d+)(\s*(#.*)?)$")
TIMEOUT_FACTOR = 4
TIMEOUT_CAP = 360


def rewrite(text: str) -> str:
    lines = text.splitlines(keepends=True)
    in_jobs = False
    blocks: list[tuple[int, int]] = []  # (start, end) line index of each job body
    starts: list[int] = []
    for i, line in enumerate(lines):
        if line.startswith("jobs:"):
            in_jobs = True
            continue
        if in_jobs and line and not line.startswith((" ", "#", "\n", "\r")):
            in_jobs = False
        if in_jobs and JOB_KEY_RE.match(line.rstrip("\n")):
            starts.append(i)
    for n, start in enumerate(starts):
        blocks.append((start, starts[n + 1] if n + 1 < len(starts) else len(lines)))

    for start, end in blocks:
        body = "".join(lines[start:end])
        if not LARGE_RE.search(body):
            continue
        for i in range(start, end):
            line = lines[i]
            if "runs-on" in line or "runner:" in line:
                for pat, repl in LABEL_RULES:
                    line = pat.sub(repl, line)
                lines[i] = line
                continue
            match = TIMEOUT_RE.match(line.rstrip("\n"))
            if match:
                new = min(int(match.group(2)) * TIMEOUT_FACTOR, TIMEOUT_CAP)
                lines[i] = f"{match.group(1)}{new}{match.group(3)}\n"
    out = "".join(lines)
    # Matrix entries / inputs that name a larger runner outside a job-level runs-on.
    for pat, repl in LABEL_RULES:
        out = pat.sub(repl, out)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    files = [Path(p) for p in args.paths] or sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    changed = []
    for path in files:
        original = path.read_text(encoding="utf-8")
        updated = rewrite(original)
        if updated != original:
            changed.append(path)
            if not args.check:
                path.write_text(updated, encoding="utf-8")
    for path in changed:
        print(("would change " if args.check else "rewrote ") + str(path.relative_to(REPO_ROOT) if path.is_absolute() else path))
    return 1 if (args.check and changed) else 0


if __name__ == "__main__":
    sys.exit(main())
