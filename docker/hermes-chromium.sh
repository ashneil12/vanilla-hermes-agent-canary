#!/bin/sh
# hermes-fork: chromium-sandbox
# The Chromium every launcher in the image runs (agent-browser through
# AGENT_BROWSER_EXECUTABLE_PATH, the Bot Desktop dock, Browser Use through
# agent-browser). It owns the one decision that matters for a browser that
# loads untrusted pages next to the agent's keys: is Chromium's sandbox on?
#
# agent-browser appends --no-sandbox by itself whenever it sees /.dockerenv,
# with no way to turn that off (cli/src/native/cdp/chrome.rs
# should_disable_sandbox, unchanged up to v0.41.1). So the flag is decided
# here, against what the kernel actually allows, not by whoever launched us:
#
#   HERMES_CHROMIUM_SANDBOX=auto     (default) sandbox on when this process can
#                                    create the user, PID and network namespaces
#                                    Chromium's namespace sandbox needs (strips
#                                    --no-sandbox); otherwise run without it and
#                                    say so on stderr.
#   HERMES_CHROMIUM_SANDBOX=require  sandbox on, or refuse to start (exit 70).
#                                    For containers given the seccomp profile in
#                                    docker/seccomp-chromium.json.
#   HERMES_CHROMIUM_SANDBOX=off      never sandbox (explicit operator opt-out).
#
# Under Docker's default seccomp profile clone/unshare with CLONE_NEWUSER is
# refused, so auto falls back to --no-sandbox there. The sandbox comes on once
# the container runs with docker/seccomp-chromium.json (moby's default plus
# clone/unshare restricted to NEWUSER|NEWPID|NEWNET), which is what Hivra's
# browser sidecar already uses.
#
#   hermes-chromium --hermes-sandbox-status   one JSON line: mode, uid, whether
#                                             the namespaces are available and
#                                             the decision a launch would take.
# scripts/chromium_sandbox_check.py proves the result on live renderer
# processes rather than trusting this decision.
set -u

real="${HERMES_CHROMIUM_REAL:-/usr/lib/chromium/chromium}"
mode="${HERMES_CHROMIUM_SANDBOX:-auto}"

case "$mode" in
    auto|require|off) ;;
    *)
        echo "hermes-chromium: HERMES_CHROMIUM_SANDBOX='$mode' must be auto, require or off" >&2
        exit 64
        ;;
esac

# Chromium refuses to sandbox as root, and its namespace sandbox needs exactly
# these three namespaces. unshare(1) asks for them in one call, as Chromium does.
namespaces_available() {
    [ "$(id -u)" != 0 ] && unshare --user --pid --net --fork true >/dev/null 2>&1
}

decide() {
    if [ "$mode" = off ]; then
        echo unsandboxed
    elif namespaces_available; then
        echo sandboxed
    elif [ "$mode" = require ]; then
        echo refused
    else
        echo unsandboxed
    fi
}

for arg in "$@"; do
    case "$arg" in
        --version|--product-version) exec "$real" "$@" ;;
        --hermes-sandbox-status)
            if namespaces_available; then ns=true; else ns=false; fi
            printf '{"mode":"%s","uid":%s,"namespaces_available":%s,"decision":"%s","chromium":"%s"}\n' \
                "$mode" "$(id -u)" "$ns" "$(decide)" "$real"
            exit 0
            ;;
    esac
done

decision="$(decide)"

# Switches that turn part of the sandbox off even when the namespaces work. require refuses them;
# auto lets an operator's explicit choice through but says the browser is not fully sandboxed.
weakening=""
for arg in "$@"; do
    case "$arg" in
        --single-process|--no-zygote|--disable-namespace-sandbox|--disable-seccomp-filter-sandbox|\
        --disable-gpu-sandbox|--disable-renderer-sandbox)
            weakening="$weakening $arg" ;;
    esac
done
if [ -n "$weakening" ] && [ "$decision" = sandboxed ]; then
    if [ "$mode" = require ]; then
        decision=refused
    else
        echo "hermes-chromium: WARNING: Chromium is running WITHOUT its sandbox fully on:$weakening" >&2
    fi
fi

if [ "$decision" = refused ]; then
    if [ -n "$weakening" ] && namespaces_available; then
        reason="it was asked to weaken the sandbox:$weakening"
    else
        reason="this process cannot create user/PID/network namespaces. Run the container as a non-root user with docker/seccomp-chromium.json as its seccomp profile."
    fi
    echo "hermes-chromium: refusing to start Chromium without its sandbox (HERMES_CHROMIUM_SANDBOX=require," \
         "uid $(id -u)): $reason" >&2
    exit 70
fi

# Rebuild argv without the flags we own.
for arg in "$@"; do
    shift
    case "$arg" in
        --no-sandbox|--disable-dev-shm-usage) continue ;;
    esac
    set -- "$@" "$arg"
done

if [ "$decision" = unsandboxed ]; then
    if [ "$mode" = auto ]; then
        echo "hermes-chromium: WARNING: Chromium is running WITHOUT its sandbox (uid $(id -u) cannot create" \
             "user/PID/network namespaces here). Give the container docker/seccomp-chromium.json to turn it on." >&2
    fi
    set -- --no-sandbox "$@"
fi

# Containers get a 64 MB /dev/shm by default; Chromium crashes mid-session on it.
exec "$real" --disable-dev-shm-usage "$@"
