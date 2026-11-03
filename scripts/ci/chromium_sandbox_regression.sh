#!/usr/bin/env bash
# hermes-fork: chromium-sandbox
# Regression gate for the built agent image (CI: .github/workflows/chromium-sandbox.yml, and the
# docker-publish / docker-build-immutable gates before any push). Proves on a real kernel that:
#   1. the only Chromium in the image is Debian's, at or above the CVE floor, and agent-browser is
#      pointed at the hermes-chromium wrapper (no Playwright Chrome for Testing left behind);
#   2. run the way Hivra's compose runs the gateway (uid 1024 with no passwd entry, entrypoint
#      bypassed) with docker/seccomp-chromium.json, Chromium's sandbox is ON: in auto and require
#      mode, and on the agent's real path (Hermes' browser tool -> agent-browser, which appends
#      --no-sandbox in every container) as read from the live renderer processes;
#   3. under Docker's default seccomp the sandbox cannot start: auto runs without it and warns,
#      require refuses to start Chromium at all, and root never gets a sandbox it cannot have.
#
# usage: scripts/ci/chromium_sandbox_regression.sh <image>
# Needs network for step 2's agent path (agent-browser comes from npx) and example.com.
set -euo pipefail

IMAGE="${1:?usage: chromium_sandbox_regression.sh <image>}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SECCOMP="$root/docker/seccomp-chromium.json"
CHECK=/opt/hermes/scripts/chromium_sandbox_check.py
[[ -f "$SECCOMP" ]] || { echo "FAIL: $SECCOMP missing" >&2; exit 1; }

# no-tmp: ok — HOME inside a throwaway --rm test container (uid 1024 has no home there)
gateway=(--rm --user 1024:1024 --entrypoint "" -e HOME=/tmp -e HERMES_HOME=/tmp/hermes-home)
profile=(--security-opt "seccomp=$SECCOMP")

fail() { echo "FAIL: $*" >&2; exit 1; }

# Runs the check script in a container; prints its JSON; returns its exit code.
check() {
  docker run "$@" python3 "$CHECK" "${CHECK_ARGS[@]}"
}

echo "== 1. one patched Chromium, behind the wrapper"
docker run --rm --entrypoint "" "$IMAGE" sh -c '
  set -eu
  test "$AGENT_BROWSER_EXECUTABLE_PATH" = /usr/local/bin/hermes-chromium
  test -x /usr/local/bin/hermes-chromium
  hermes-chromium --version
  stray=$(find / -xdev -type f \( -name chrome-headless-shell -o -name headless_shell -o -path "*/chrome-linux*/chrome" \) 2>/dev/null || true)
  if [ -n "$stray" ]; then echo "Chrome for Testing still in the image: $stray" >&2; exit 1; fi
' || fail "the image does not ship exactly the wrapped Debian chromium"

echo "== 2a. gateway shape + seccomp profile, auto: sandboxed"
CHECK_ARGS=(--expect sandboxed)
check "${gateway[@]}" "${profile[@]}" "$IMAGE" || fail "auto mode is not sandboxed under the seccomp profile"

echo "== 2b. gateway shape + seccomp profile, require: sandboxed"
check "${gateway[@]}" "${profile[@]}" -e HERMES_CHROMIUM_SANDBOX=require "$IMAGE" \
  || fail "require mode is not sandboxed under the seccomp profile"

echo "== 2c. the agent's real path: browser_navigate -> agent-browser -> hermes-chromium"
# The check runs while the tool's browser is still open: Hermes closes it at interpreter exit.
docker run "${gateway[@]}" "${profile[@]}" -e HERMES_CHROMIUM_SANDBOX=require -w /opt/hermes "$IMAGE" sh -c '
  mkdir -p "$HERMES_HOME" && exec /opt/hermes/.venv/bin/python - <<PY
import json, subprocess, sys
from tools.browser_tool import browser_navigate
from tools.browser_tool_lifecycle import cleanup_all_browsers
result = json.loads(browser_navigate("https://example.com", task_id="sandbox-regression"))
print(json.dumps({k: result.get(k) for k in ("success", "title", "url", "error")}))
if not result.get("success"):
    sys.exit(1)
try:
    sys.exit(subprocess.run(["python3", "'"$CHECK"'", "--running", "--expect", "sandboxed"]).returncode)
finally:
    cleanup_all_browsers()
PY
' || fail "the agent's browser is not sandboxed on its real launch path"

echo "== 2d. Browser Use's path: the packaged Chromium its CLI attaches to over CDP"
docker run "${gateway[@]}" "${profile[@]}" -e HERMES_CHROMIUM_SANDBOX=require -w /opt/hermes "$IMAGE" sh -c '
  mkdir -p "$HERMES_HOME" && exec /opt/hermes/.venv/bin/python - <<PY
import subprocess, sys
from tools.browser_use_cli import _resolve_managed_chromium_cdp
from tools.browser_tool_lifecycle import cleanup_all_browsers
env = {}
error = _resolve_managed_chromium_cdp(env, "sandbox-regression-bu")
print({"error": error, "cdp": sorted(k for k in env if k.startswith("BU_CDP"))})
if error or not any(k.startswith("BU_CDP") for k in env):
    sys.exit(1)
try:
    sys.exit(subprocess.run(["python3", "'"$CHECK"'", "--running", "--expect", "sandboxed"]).returncode)
finally:
    cleanup_all_browsers()
PY
' || fail "Browser Use's Chromium is not sandboxed"

echo "== 3a. Docker default seccomp, auto: runs without the sandbox and says so"
CHECK_ARGS=(--expect unsandboxed)
out="$(check "${gateway[@]}" "$IMAGE")" || fail "auto mode did not degrade as documented: $out"
echo "$out"
grep -q '"wrapper_warning": true' <<<"$out" || fail "auto mode ran unsandboxed without the warning"

echo "== 3b. Docker default seccomp, require: refuses to start"
CHECK_ARGS=(--expect refused)
check "${gateway[@]}" -e HERMES_CHROMIUM_SANDBOX=require "$IMAGE" || fail "require mode started Chromium without its sandbox"

echo "== 3c. root, require, even with the profile: refuses to start"
# no-tmp: ok — HOME inside a throwaway --rm test container
check --rm --user 0:0 --entrypoint "" -e HOME=/tmp "${profile[@]}" -e HERMES_CHROMIUM_SANDBOX=require "$IMAGE" \
  || fail "require mode started Chromium as root"

echo "PASS: $IMAGE ships a patched Chromium whose sandbox is on wherever the container allows it"
