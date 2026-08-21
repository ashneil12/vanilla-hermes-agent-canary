#!/usr/bin/env bash
# Import release tags from the authoritative upstream repository.

set -euo pipefail

REPO=""
REMOTE="https://github.com/NousResearch/hermes-agent.git"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo)
      [ "$#" -ge 2 ] || { echo 'error: --repo needs a value' >&2; exit 1; }
      REPO="$2"; shift 2 ;;
    --remote)
      [ "$#" -ge 2 ] || { echo 'error: --remote needs a value' >&2; exit 1; }
      REMOTE="$2"; shift 2 ;;
    -h|--help)
      echo 'usage: fetch-release-tags.sh [--repo DIR] [--remote URL]'
      exit 0 ;;
    *)
      echo "error: unknown argument: $1" >&2
      exit 1 ;;
  esac
done

if [ -z "$REPO" ]; then
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  REPO="$(git -C "$script_dir" rev-parse --show-toplevel)"
fi

echo "Fetching authoritative release tags from $REMOTE"
git -C "$REPO" fetch --force --no-tags "$REMOTE" \
  '+refs/tags/v*:refs/tags/v*'

count="$(git -C "$REPO" tag --list 'v*' \
  | grep -Ec '^v[0-9]{4}\.[0-9]+\.[0-9]+(\.[0-9]+)?$' || true)"
if [ "$count" -eq 0 ]; then
  echo "error: authoritative remote published no release tags: $REMOTE" >&2
  exit 1
fi
echo "Imported $count release tag(s)"
