#!/usr/bin/env python3
# hermes-fork: chromium-sandbox
"""Prove, on live processes, whether the image's Chromium is patched and sandboxed.

Chromium's own report (chrome://sandbox) does not load in headless mode, so this reads the
kernel instead. With the namespace sandbox on, every renderer runs in its own user, PID and
network namespace and carries Chromium's seccomp-BPF filter on top of the container's; with
--no-sandbox the renderers share the browser's namespaces and filters.

  chromium_sandbox_check.py            launch the image's Chromium the way agent-browser does in a
                                       container (it appends --no-sandbox) and inspect its renderers
  chromium_sandbox_check.py --running  inspect the Chromium browsers already running as this user
                                       (after the agent browsed: proves the real launch path)
  --expect sandboxed|unsandboxed|refused   what a pass is (default: sandboxed)

Prints one JSON object. Exit 0 when the version is at or above the floor and the result matches
--expect, 1 otherwise. Standard library only: it runs under the system python3 of the image and
on audits inside a running gateway container.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

# Oldest Chromium the image may ship: CVE-2026-118306 (sandbox escape) is fixed in 156.0.8078.73.
# Must equal CHROMIUM_MIN_VERSION in the Dockerfile; tests/tools/test_chromium_sandbox.py pins both.
MIN_CHROMIUM_VERSION = "156.0.8078.73"
DEFAULT_EXECUTABLE = "/usr/local/bin/hermes-chromium"
DEFAULT_REAL = "/usr/lib/chromium/chromium"
WRAPPER_REFUSED = 70  # docker/hermes-chromium.sh's exit code when require mode refuses
_PAGE = "data:text/html,<title>hermes-sandbox-check</title><p>sandbox check</p>"


def version_tuple(text):
    match = re.search(r"(\d+)\.(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(part) for part in match.groups()) if match else None


def chromium_version(executable):
    out = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=30)
    return (out.stdout or out.stderr).strip()


def _read(path, binary=False):
    try:
        with open(path, "rb" if binary else "r") as handle:
            return handle.read()
    except OSError:
        return None


def _cmdline(pid):
    # Chromium rewrites its children's process title, so their cmdline is one space-joined
    # string rather than NUL-separated argv: split on both.
    raw = _read(f"/proc/{pid}/cmdline", binary=True)
    return raw.replace(b"\0", b" ").decode(errors="replace").split() if raw else []


def _ns(pid, kind):
    try:
        return os.readlink(f"/proc/{pid}/ns/{kind}")
    except OSError:
        return None


def _seccomp_filters(pid):
    status = _read(f"/proc/{pid}/status") or ""
    match = re.search(r"^Seccomp_filters:\s*(\d+)", status, re.M)
    return int(match.group(1)) if match else None


def _ppid(pid):
    stat = _read(f"/proc/{pid}/stat") or ""
    # The comm field may contain spaces and parentheses; ppid is the 2nd field after the last ')'.
    tail = stat.rsplit(")", 1)[-1].split()
    return int(tail[1]) if len(tail) > 1 else None


def _pids():
    return [int(name) for name in os.listdir("/proc") if name.isdigit()]


def _descendants(root):
    children = {}
    for pid in _pids():
        parent = _ppid(pid)
        if parent is not None:
            children.setdefault(parent, []).append(pid)
    found, stack = [], [root]
    while stack:
        for child in children.get(stack.pop(), []):
            found.append(child)
            stack.append(child)
    return found


def _process_type(cmdline):
    for arg in cmdline:
        if arg.startswith("--type="):
            return arg.split("=", 1)[1]
    return "browser"


def inspect_browser(browser_pid):
    """Sandbox facts for one browser process and its renderer descendants."""
    browser = {
        "pid": browser_pid,
        "no_sandbox_flag": "--no-sandbox" in _cmdline(browser_pid),
        "user": _ns(browser_pid, "user"), "pid_ns": _ns(browser_pid, "pid"), "net": _ns(browser_pid, "net"),
        "seccomp_filters": _seccomp_filters(browser_pid),
    }
    renderers = []
    for pid in _descendants(browser_pid):
        cmdline = _cmdline(pid)
        if _process_type(cmdline) != "renderer":
            continue
        filters = _seccomp_filters(pid)
        renderers.append({
            "pid": pid,
            "own_user_ns": _ns(pid, "user") not in (None, browser["user"]),
            "own_pid_ns": _ns(pid, "pid") not in (None, browser["pid_ns"]),
            "own_net_ns": _ns(pid, "net") not in (None, browser["net"]),
            "extra_seccomp_filter": None not in (filters, browser["seccomp_filters"])
                                    and filters > browser["seccomp_filters"],
            "no_sandbox_flag": "--no-sandbox" in cmdline,
        })
    sandboxed = bool(renderers) and not browser["no_sandbox_flag"] and all(
        r["own_user_ns"] and r["own_pid_ns"] and r["own_net_ns"] and r["extra_seccomp_filter"]
        and not r["no_sandbox_flag"] for r in renderers)
    return {"browser": browser, "renderers": renderers, "sandboxed": sandboxed}


def _wait_for_renderer(pid, deadline):
    while time.monotonic() < deadline:
        report = inspect_browser(pid)
        if report["renderers"]:
            return report
        time.sleep(0.25)
    return inspect_browser(pid)


def launch_and_inspect(executable, timeout):
    """Launch like agent-browser does in a container and inspect the result."""
    profile = tempfile.mkdtemp(prefix="hermes-sandbox-check-")
    stderr = tempfile.TemporaryFile()
    argv = [executable, "--headless=new", "--no-first-run", "--no-default-browser-check",
            f"--user-data-dir={profile}", "--remote-debugging-port=0", "--no-sandbox", _PAGE]
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=stderr)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and proc.poll() is None and not _descendants(proc.pid):
            time.sleep(0.1)
        if proc.poll() is not None:
            stderr.seek(0)
            err = stderr.read().decode(errors="replace")
            # Only the wrapper's deliberate refusal counts; any other early exit is a crash.
            refused = proc.returncode == WRAPPER_REFUSED and "refusing to start Chromium" in err
            return {"outcome": "refused" if refused else "crashed", "exit_code": proc.returncode,
                    "stderr": err[-1500:]}
        report = _wait_for_renderer(proc.pid, deadline)
        stderr.seek(0)
        report["outcome"] = "sandboxed" if report["sandboxed"] else (
            "unsandboxed" if report["renderers"] else "no_renderer")
        report["wrapper_warning"] = "WITHOUT its sandbox" in stderr.read().decode(errors="replace")
        return report
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        stderr.close()
        shutil.rmtree(profile, ignore_errors=True)


def inspect_running(real):
    """Every running Chromium browser process (not a child) owned by this user."""
    real = os.path.realpath(real)
    browsers = []
    for pid in _pids():
        try:
            if os.path.realpath(os.readlink(f"/proc/{pid}/exe")) != real:
                continue
        except OSError:
            continue
        if _process_type(_cmdline(pid)) == "browser":
            browsers.append(inspect_browser(pid))
    if not browsers:
        return {"outcome": "no_browser", "browsers": []}
    if any(not b["renderers"] for b in browsers):
        outcome = "no_renderer"
    else:
        outcome = "sandboxed" if all(b["sandboxed"] for b in browsers) else "unsandboxed"
    return {"outcome": outcome, "browsers": browsers}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--executable", default=os.environ.get("AGENT_BROWSER_EXECUTABLE_PATH") or DEFAULT_EXECUTABLE)
    parser.add_argument("--real", default=os.environ.get("HERMES_CHROMIUM_REAL") or DEFAULT_REAL,
                        help="the Chromium binary behind the wrapper (matched for --running)")
    parser.add_argument("--min-version", default=MIN_CHROMIUM_VERSION)
    parser.add_argument("--expect", choices=("sandboxed", "unsandboxed", "refused"), default="sandboxed")
    parser.add_argument("--running", action="store_true")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)

    version_text = chromium_version(args.executable)
    version = version_tuple(version_text)
    floor = version_tuple(args.min_version)
    result = {"executable": args.executable, "version": version_text, "min_version": args.min_version,
              "version_ok": bool(version and floor and version >= floor), "uid": os.getuid(),
              "mode": os.environ.get("HERMES_CHROMIUM_SANDBOX", "auto"), "expect": args.expect}
    result.update(inspect_running(args.real) if args.running else launch_and_inspect(args.executable, args.timeout))
    result["ok"] = result["version_ok"] and result["outcome"] == args.expect
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
