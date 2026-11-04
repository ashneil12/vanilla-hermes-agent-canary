"""hermes-fork: chromium-sandbox — the image's Chromium is patched and its sandbox is decided in one place.

The image ships Debian's chromium (security-tracked, with a build-time CVE floor) behind
docker/hermes-chromium.sh, which agent-browser and the Bot Desktop dock launch through
AGENT_BROWSER_EXECUTABLE_PATH. agent-browser appends --no-sandbox in every container, so the wrapper,
not the launcher, decides: sandbox on when the kernel allows the namespaces, refuse in require mode.
The image-level proof on a real kernel is scripts/ci/chromium_sandbox_regression.sh.
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WRAPPER = REPO / "docker" / "hermes-chromium.sh"
CHECK_SCRIPT = REPO / "scripts" / "chromium_sandbox_check.py"
DOCKERFILE = REPO / "Dockerfile"
SECCOMP = REPO / "docker" / "seccomp-chromium.json"

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="the wrapper is a POSIX sh script")


def _load_check_script():
    spec = importlib.util.spec_from_file_location("chromium_sandbox_check", CHECK_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stub(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _run_wrapper(tmp_path, args, *, mode=None, uid=1024, namespaces=True):
    """Run the real wrapper with stub chromium/unshare/id on PATH; return (code, argv, stderr)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    argv_file = tmp_path / "argv"
    _stub(bin_dir / "chromium", f'for a; do printf "%s\\n" "$a"; done > "{argv_file}"\n')
    _stub(bin_dir / "unshare", f"exit {0 if namespaces else 1}\n")
    _stub(bin_dir / "id", f'[ "$1" = -u ] && echo {uid}\n')
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HERMES_CHROMIUM_REAL": str(bin_dir / "chromium")}
    if mode is not None:
        env["HERMES_CHROMIUM_SANDBOX"] = mode
    proc = subprocess.run(["sh", str(WRAPPER), *args], env=env, capture_output=True, text=True, timeout=30)
    argv = argv_file.read_text().splitlines() if argv_file.exists() else None
    return proc.returncode, argv, proc.stderr, proc.stdout


AGENT_BROWSER_ARGS = ["--headless=new", "--remote-debugging-port=0", "--no-sandbox", "--disable-dev-shm-usage",
                      "about:blank"]


@posix_only
class TestWrapperDecision:
    def test_sandbox_on_strips_the_no_sandbox_agent_browser_appends(self, tmp_path):
        code, argv, stderr, _ = _run_wrapper(tmp_path, AGENT_BROWSER_ARGS)
        assert code == 0
        assert "--no-sandbox" not in argv
        assert argv.count("--disable-dev-shm-usage") == 1
        assert argv[-1] == "about:blank" and "--headless=new" in argv
        assert "WITHOUT its sandbox" not in stderr

    def test_require_keeps_the_sandbox_on_when_available(self, tmp_path):
        code, argv, _, _ = _run_wrapper(tmp_path, AGENT_BROWSER_ARGS, mode="require")
        assert code == 0 and "--no-sandbox" not in argv

    def test_auto_without_namespaces_runs_unsandboxed_and_warns(self, tmp_path):
        code, argv, stderr, _ = _run_wrapper(tmp_path, ["about:blank"], namespaces=False)
        assert code == 0
        assert argv.count("--no-sandbox") == 1
        assert "WITHOUT its sandbox" in stderr

    def test_require_without_namespaces_refuses_and_never_starts_chromium(self, tmp_path):
        code, argv, stderr, _ = _run_wrapper(tmp_path, AGENT_BROWSER_ARGS, mode="require", namespaces=False)
        assert code == 70
        assert argv is None
        assert "refusing to start Chromium without its sandbox" in stderr

    def test_root_runs_unsandboxed_in_auto(self, tmp_path):
        code, argv, _, _ = _run_wrapper(tmp_path, ["about:blank"], uid=0, namespaces=True)
        assert code == 0 and argv.count("--no-sandbox") == 1

    def test_root_is_refused_in_require(self, tmp_path):
        code, argv, _, _ = _run_wrapper(tmp_path, ["about:blank"], uid=0, mode="require", namespaces=True)
        assert code == 70 and argv is None

    def test_require_refuses_switches_that_weaken_the_sandbox(self, tmp_path):
        code, argv, stderr, _ = _run_wrapper(tmp_path, ["--single-process", "about:blank"], mode="require")
        assert code == 70 and argv is None
        assert "weaken the sandbox: --single-process" in stderr

    def test_auto_warns_when_a_switch_weakens_the_sandbox(self, tmp_path):
        code, argv, stderr, _ = _run_wrapper(tmp_path, ["--disable-seccomp-filter-sandbox", "about:blank"])
        assert code == 0 and "--disable-seccomp-filter-sandbox" in argv and "--no-sandbox" not in argv
        assert "WITHOUT its sandbox fully on: --disable-seccomp-filter-sandbox" in stderr

    def test_off_is_an_explicit_opt_out(self, tmp_path):
        code, argv, stderr, _ = _run_wrapper(tmp_path, ["about:blank"], mode="off")
        assert code == 0 and argv.count("--no-sandbox") == 1
        assert "WITHOUT its sandbox" not in stderr

    def test_unknown_mode_is_rejected(self, tmp_path):
        code, argv, stderr, _ = _run_wrapper(tmp_path, ["about:blank"], mode="yes")
        assert code == 64 and argv is None and "must be auto, require or off" in stderr

    def test_version_passes_straight_through(self, tmp_path):
        code, argv, _, _ = _run_wrapper(tmp_path, ["--version"], mode="require", namespaces=False)
        assert code == 0 and argv == ["--version"]

    def test_status_reports_the_decision(self, tmp_path):
        code, _, _, out = _run_wrapper(tmp_path, ["--hermes-sandbox-status"], mode="require", namespaces=False)
        assert code == 0
        status = json.loads(out)
        assert status["decision"] == "refused" and status["namespaces_available"] is False
        assert status["uid"] == 1024 and status["mode"] == "require"


class TestPythonDefersToTheWrapper:
    @pytest.fixture
    def wrapper_exe(self, tmp_path):
        exe = tmp_path / "hermes-chromium"
        _stub(exe, "exit 0\n")
        return str(exe)

    def test_no_bypass_injected_when_the_wrapper_is_the_browser(self, monkeypatch, wrapper_exe):
        from tools import browser_tool_session as session

        monkeypatch.setattr(session._install, "_running_in_docker", lambda: True)
        monkeypatch.setattr(session.os, "geteuid", lambda: 0)
        monkeypatch.setenv("AGENT_BROWSER_EXECUTABLE_PATH", wrapper_exe)
        assert session._needs_chromium_sandbox_bypass() is False
        env: dict = {}
        session._apply_chromium_sandbox_args(env)
        assert "AGENT_BROWSER_ARGS" not in env

    def test_wrapper_pinned_in_the_launch_env_is_honoured(self, monkeypatch, wrapper_exe):
        from tools import browser_tool_session as session

        monkeypatch.delenv("AGENT_BROWSER_EXECUTABLE_PATH", raising=False)
        monkeypatch.setattr(session._install, "_running_in_docker", lambda: True)
        env = {"AGENT_BROWSER_EXECUTABLE_PATH": wrapper_exe}
        session._apply_chromium_sandbox_args(env)
        assert "AGENT_BROWSER_ARGS" not in env

    def test_other_browsers_keep_the_upstream_policy(self, monkeypatch, tmp_path):
        from tools import browser_tool_session as session

        other = tmp_path / "chrome-headless-shell"
        _stub(other, "exit 0\n")
        monkeypatch.setenv("AGENT_BROWSER_EXECUTABLE_PATH", str(other))
        monkeypatch.setattr(session._install, "_running_in_docker", lambda: True)
        env: dict = {}
        session._apply_chromium_sandbox_args(env)
        assert env["AGENT_BROWSER_ARGS"] == "--no-sandbox,--disable-dev-shm-usage"

    def test_a_missing_wrapper_is_not_trusted(self, monkeypatch, tmp_path):
        from tools import browser_tool_session as session

        monkeypatch.setenv("AGENT_BROWSER_EXECUTABLE_PATH", str(tmp_path / "hermes-chromium"))
        monkeypatch.setattr(session._install, "_running_in_docker", lambda: True)
        assert session._needs_chromium_sandbox_bypass() is True

    def test_dock_and_agent_share_the_wrapper_decision(self, monkeypatch, wrapper_exe):
        from tools.bot_desktop import browser

        monkeypatch.setenv("AGENT_BROWSER_EXECUTABLE_PATH", wrapper_exe)
        assert browser.executable() == wrapper_exe
        assert "--no-sandbox" not in browser.dock_argv(wrapper_exe, "/p/dir")


class TestImageContract:
    def test_floor_is_the_same_in_the_dockerfile_and_the_check(self):
        match = re.search(r"^ARG CHROMIUM_MIN_VERSION=(\S+)$", DOCKERFILE.read_text(encoding="utf-8"), re.M)
        assert match, "Dockerfile lost its Chromium security floor"
        check = _load_check_script()
        assert match.group(1) == check.MIN_CHROMIUM_VERSION
        assert check.version_tuple(check.MIN_CHROMIUM_VERSION) >= (156, 0, 8078, 73)  # CVE-2026-118306

    def test_dockerfile_installs_debian_chromium_behind_the_wrapper_and_no_chrome_for_testing(self):
        text = DOCKERFILE.read_text(encoding="utf-8")
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        assert "playwright install" not in code, "Playwright's Chrome for Testing is unpatched; use Debian's chromium"
        assert re.search(r"dpkg --compare-versions \"\$installed\" ge \"\$CHROMIUM_MIN_VERSION\"", code)
        assert "COPY --chmod=0755 docker/hermes-chromium.sh /usr/local/bin/hermes-chromium" in code
        assert "ENV AGENT_BROWSER_EXECUTABLE_PATH=/usr/local/bin/hermes-chromium" in code
        assert _load_check_script().DEFAULT_EXECUTABLE == "/usr/local/bin/hermes-chromium"

    def test_seccomp_profile_only_opens_the_three_sandbox_namespaces(self):
        profile = json.loads(SECCOMP.read_text(encoding="utf-8"))
        assert profile["defaultAction"] == "SCMP_ACT_ERRNO"
        clone_newuser, clone_newpid, clone_newnet = 0x10000000, 0x20000000, 0x40000000
        blocked = 0x00020000 | 0x02000000 | 0x04000000 | 0x08000000  # NEWNS, NEWCGROUP, NEWUTS, NEWIPC
        unprivileged = [rule for rule in profile["syscalls"]
                        if "unshare" in rule["names"] and "caps" not in rule.get("includes", {})]
        assert len(unprivileged) == 1
        (arg,) = unprivileged[0]["args"]
        assert arg["op"] == "SCMP_CMP_MASKED_EQ" and arg["value"] == blocked and arg.get("valueTwo", 0) == 0
        assert not blocked & (clone_newuser | clone_newpid | clone_newnet)
        assert set(unprivileged[0]["names"]) == {"clone", "unshare"}
        setns = [rule for rule in profile["syscalls"] if "setns" in rule["names"]]
        assert all("CAP_SYS_ADMIN" in rule.get("includes", {}).get("caps", []) for rule in setns)


class TestCheckScript:
    @pytest.mark.skipif(not sys.platform.startswith("linux"), reason="reads /proc")
    def test_refused_means_the_wrapper_refused_not_any_crash(self, tmp_path):
        check = _load_check_script()
        crash = tmp_path / "crash"
        _stub(crash, "exit 1\n")
        assert check.launch_and_inspect(str(crash), 10)["outcome"] == "crashed"
        refuse = tmp_path / "refuse"
        _stub(refuse, 'echo "hermes-chromium: refusing to start Chromium without its sandbox" >&2; exit 70\n')
        assert check.launch_and_inspect(str(refuse), 10)["outcome"] == "refused"

    def test_version_parsing_and_floor(self):
        check = _load_check_script()
        assert check.version_tuple("Chromium 156.0.8078.79 ") == (156, 0, 8078, 79)
        assert check.version_tuple("Google Chrome for Testing 151.0.7922.34") < check.version_tuple(
            check.MIN_CHROMIUM_VERSION)
        assert check.version_tuple("no version here") is None

    def test_renderer_type_is_read_from_a_rewritten_process_title(self, monkeypatch):
        """Chromium rewrites its children's cmdline as one space-joined string."""
        check = _load_check_script()
        titles = {
            1: b"/usr/lib/chromium/chromium\0--headless=new\0",
            2: b"/usr/lib/chromium/chromium --type=renderer --lang=en-US",
        }
        monkeypatch.setattr(check, "_read", lambda path, binary=False: titles.get(int(path.split("/")[2])))
        assert check._process_type(check._cmdline(1)) == "browser"
        assert check._process_type(check._cmdline(2)) == "renderer"

    @pytest.mark.skipif(not sys.platform.startswith("linux"), reason="reads /proc")
    def test_inspect_flags_renderers_that_share_the_browser_namespaces(self, monkeypatch):
        check = _load_check_script()
        facts = {
            10: ("browser", "user:[1]", "pid:[1]", "net:[1]", 1),
            11: ("renderer", "user:[2]", "pid:[2]", "net:[2]", 2),
            12: ("renderer", "user:[1]", "pid:[1]", "net:[1]", 1),
        }
        monkeypatch.setattr(check, "_descendants", lambda pid: [11, 12])
        monkeypatch.setattr(check, "_cmdline", lambda pid: [f"--type={facts[pid][0]}"] if pid != 10 else [])
        monkeypatch.setattr(check, "_ns", lambda pid, kind: facts[pid][{"user": 1, "pid": 2, "net": 3}[kind]])
        monkeypatch.setattr(check, "_seccomp_filters", lambda pid: facts[pid][4])
        report = check.inspect_browser(10)
        assert [r["own_user_ns"] for r in report["renderers"]] == [True, False]
        assert report["sandboxed"] is False
        monkeypatch.setattr(check, "_descendants", lambda pid: [11])
        assert check.inspect_browser(10)["sandboxed"] is True
