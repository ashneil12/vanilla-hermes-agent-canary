"""Container-only worker for gateway_lock_regression.py.

Never run this worker against an existing Hermes home. The driver supplies a
new labeled tmpfs volume, an isolated PID namespace, and no network or secrets.
"""

import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time


PROTOCOL = "hermes-lock-regression-v1"
ROOT = Path("/opt/data")
CASES = ("default", "explicit-profile")
WORKER_SECONDS = 90
ROLE = sys.argv[1]
RUN_ID = sys.argv[2]
CHECK = "worker-preflight"
DEADLINE = time.monotonic() + WORKER_SECONDS


def require(condition, check):
    global CHECK
    CHECK = check
    if not condition:
        raise AssertionError(check)


def alarm_handler(signum, frame):
    raise TimeoutError("worker deadline or termination")


def remaining():
    if time.monotonic() >= DEADLINE:
        raise TimeoutError("worker deadline")


def publish(name, payload):
    remaining()
    target = ROOT / name
    require(not target.exists(), "receipt-not-reused")
    temporary = ROOT / (name + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump({"run_id": RUN_ID, **payload}, stream, separators=(",", ":"))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)


def receive(name):
    target = ROOT / name
    while True:
        remaining()
        if target.exists():
            require(target.stat().st_size < 16_384, "receipt-size")
            payload = json.loads(target.read_text(encoding="utf-8"))
            require(payload.get("run_id") == RUN_ID, "receipt-run-id")
            return payload
        time.sleep(0.05)


def fingerprint(path):
    require(path.is_file() and not path.is_symlink(), "regular-test-file")
    info = path.stat()
    require(info.st_size < 16_384, "test-file-size")
    data = path.read_bytes()
    return {
        "inode": info.st_ino,
        "device": info.st_dev,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }


def identity_files(home):
    return {name: fingerprint(home / name) for name in ("gateway.pid", "gateway.lock")}


def check_other_profile(control, expected):
    require(fingerprint(control / "sentinel") == expected, "other-profile-sentinel")
    require(sorted(path.name for path in control.iterdir()) == ["sentinel"], "other-profile-unchanged")


def prepare_fixture():
    # gateway package imports load_config(), which creates a Hermes home.
    # Prove freshness before either import, then isolate those side effects
    # from both lock fixtures and the control profile.
    if ROLE == "owner":
        require(not list(ROOT.iterdir()), "fresh-empty-test-volume")
        control = ROOT / "control"
        control.mkdir(mode=0o700)
        (control / "sentinel").write_text(RUN_ID, encoding="utf-8")
        publish("fixture-ready.json", {})
    else:
        receive("fixture-ready.json")
    import_home = ROOT / ("import-" + ROLE)
    require(not import_home.exists(), "fresh-role-import-home")
    import_home.mkdir(mode=0o700)
    return import_home


def check_owner_record(status, home, ready, namespace):
    # Each process is PID 1, but they are different processes in different
    # namespaces. The reader must not treat its own unrelated Python PID as
    # the lock owner's gateway, even though the number exists locally.
    require(ready["pid"] == os.getpid() == 1, "real-pid-collision")
    require(ready["namespace"] != namespace, "separate-pid-namespaces")
    record = json.loads((home / "gateway.pid").read_text(encoding="utf-8"))
    require(record["pid"] == ready["pid"], "owner-record-pid")
    require(status._pid_exists(record["pid"]), "colliding-pid-exists")
    require(bool(status._read_process_cmdline(record["pid"])), "live-command-readable")
    require(not status._record_matches_live_gateway_pid(record, record["pid"]), "unrelated-local-pid-rejected")


def check_sqlite_runtime():
    """Qualify this image interpreter without opening any on-disk database."""
    global CHECK
    import sqlite3

    from hermes_cli.sqlite_runtime import is_sqlite_wal_reset_vulnerable

    vulnerable = is_sqlite_wal_reset_vulnerable(sqlite3.sqlite_version_info)
    require(not vulnerable, "sqlite-wal-reset-fixed:" + sqlite3.sqlite_version)
    CHECK = "sqlite-fts5-trigram"
    db = sqlite3.connect(":memory:")
    try:
        # Same runtime contract as tests/docker/test_sqlite_runtime.py: a
        # safe library must also retain the trigram tokenizer Hermes uses.
        db.execute("CREATE VIRTUAL TABLE docs USING fts5(content, tokenize='trigram')")
        db.execute("INSERT INTO docs VALUES ('hermes')")
        matches = db.execute("SELECT count(*) FROM docs WHERE docs MATCH 'erm'").fetchone()[0]
        source_id = db.execute("SELECT sqlite_source_id()").fetchone()[0]
    finally:
        db.close()
    require(matches == 1, "sqlite-fts5-trigram")
    return {
        "executable": sys.executable, "python_version": list(sys.version_info[:3]),
        "sqlite_version": sqlite3.sqlite_version, "sqlite_source_id": source_id,
        "wal_reset_vulnerable": vulnerable, "trigram_matches": matches,
    }


def owner(status, namespace):
    sqlite_runtime = check_sqlite_runtime()
    control = ROOT / "control"
    control_before = fingerprint(control / "sentinel")
    for case in CASES:
        home = ROOT / case
        home.mkdir(mode=0o700)
        os.environ["HERMES_HOME"] = str(home)
        require(status.acquire_gateway_runtime_lock(), "owner-acquires-lock")
        status.write_pid_file()
        before = identity_files(home)
        require(status.is_gateway_runtime_lock_active(), "owner-lock-active")
        publish(case + ".owner-ready.json", {
            "pid": os.getpid(), "namespace": namespace,
            "files": before, "control": control_before,
        })
        receive(case + ".reader-held.json")
        require(identity_files(home) == before, "owner-original-inodes-preserved")
        require(status.is_gateway_runtime_lock_active(), "owner-still-holds-lock")

        # Actual release closes the handle but deliberately does not unlink
        # either identity file. The reader tests stale-file cleanup next.
        status.release_gateway_runtime_lock()
        require(not status.is_gateway_runtime_lock_active(), "owner-release-effective")
        require(identity_files(home) == before, "release-keeps-metadata")
        publish(case + ".owner-released.json", {})
        receive(case + ".reader-reacquired.json")
        require(status.is_gateway_runtime_lock_active(), "reader-new-lock-active")
        require(not status.acquire_gateway_runtime_lock(), "owner-cannot-steal-reader-lock")
        check_other_profile(control, control_before)
        publish(case + ".owner-verified.json", {})
        receive(case + ".reader-done.json")
        require(not (home / "gateway.pid").exists(), "reader-final-pid-cleanup")
        require(not (home / "gateway.lock").exists(), "reader-final-lock-cleanup")
    return {"cases": list(CASES), "handoff_verified": True, "sqlite_runtime": sqlite_runtime}


def reader(status, namespace):
    control = ROOT / "control"
    for case in CASES:
        ready = receive(case + ".owner-ready.json")
        home = ROOT / case
        lookup = None if case == "default" else home / "gateway.pid"
        process_home = home if lookup is None else control
        os.environ["HERMES_HOME"] = str(process_home)
        check_owner_record(status, home, ready, namespace)
        before = identity_files(home)
        require(before == ready["files"], "reader-sees-owner-inodes")
        require(status.is_gateway_runtime_lock_active(home / "gateway.lock"), "reader-observes-held-lock")
        require(status.get_running_pid(lookup) is None, "no-unvalidated-pid-returned")
        require(identity_files(home) == before, "held-files-preserved")
        require(status.is_gateway_runtime_lock_active(home / "gateway.lock"), "original-lock-remains-held")
        check_other_profile(control, ready["control"])

        os.environ["HERMES_HOME"] = str(home)
        require(not status.acquire_gateway_runtime_lock(), "second-acquisition-denied")
        os.environ["HERMES_HOME"] = str(process_home)
        publish(case + ".reader-held.json", {})
        receive(case + ".owner-released.json")
        require(not status.is_gateway_runtime_lock_active(home / "gateway.lock"), "released-lock-inactive")
        require(status.get_running_pid(lookup, cleanup_stale=False) is None, "stale-read-only-result")
        require(identity_files(home) == before, "stale-read-only-preserves-files")
        require(status.get_running_pid(lookup) is None, "stale-cleanup-result")
        require(not (home / "gateway.pid").exists(), "stale-pid-removed")
        require(not (home / "gateway.lock").exists(), "stale-lock-removed")
        check_other_profile(control, ready["control"])

        os.environ["HERMES_HOME"] = str(home)
        require(status.acquire_gateway_runtime_lock(), "reacquisition-succeeds")
        status.write_pid_file()
        require(status.is_gateway_runtime_lock_active(), "reader-owns-new-lock")
        publish(case + ".reader-reacquired.json", {})
        receive(case + ".owner-verified.json")
        status.remove_pid_file()
        status.release_gateway_runtime_lock()
        require(status.get_running_pid() is None, "final-cleanup-result")
        require(not (home / "gateway.pid").exists(), "final-pid-absent")
        require(not (home / "gateway.lock").exists(), "final-lock-absent")
        check_other_profile(control, ready["control"])
        publish(case + ".reader-done.json", {})
    return {
        "cases": list(CASES), "pid_collision_rejected": True,
        "held_files_preserved": True, "second_acquisition_denied": True,
        "release_cleanup_reacquisition": True, "other_profile_preserved": True,
    }


def main():
    status = None
    arm_alarm = None
    try:
        # Reject unsupported hosts before touching POSIX-only primitives.
        require(sys.platform.startswith("linux"), "linux-worker")
        alarm_signal = getattr(signal, "SIGALRM", None)
        arm_alarm = getattr(signal, "alarm", None)
        get_uid = getattr(os, "getuid", None)
        get_gid = getattr(os, "getgid", None)
        require(
            alarm_signal is not None and callable(arm_alarm)
            and callable(get_uid) and callable(get_gid),
            "linux-worker-primitives",
        )
        signal.signal(alarm_signal, alarm_handler)
        signal.signal(signal.SIGTERM, alarm_handler)
        arm_alarm(WORKER_SECONDS)
        require(ROLE in ("owner", "reader") and len(RUN_ID) == 32, "worker-arguments")
        require(get_uid() == get_gid() == 10000, "unprivileged-worker")
        require(os.getpid() == 1, "private-pid-one")
        require(ROOT.is_dir() and ROOT.stat().st_uid == 10000, "test-volume-owner")
        os.environ["HERMES_HOME"] = str(prepare_fixture())
        os.environ["HERMES_DISABLE_LAZY_INSTALLS"] = "1"
        sys.path.insert(0, "/opt/hermes")
        from gateway import status
        require(Path(status.__file__).resolve() == Path("/opt/hermes/gateway/status.py"), "image-status-module")
        namespace = os.readlink("/proc/self/ns/pid")
        details = owner(status, namespace) if ROLE == "owner" else reader(status, namespace)
        print(json.dumps({
            "protocol": PROTOCOL, "run_id": RUN_ID, "role": ROLE,
            "result": "PASS", "namespace": namespace, **details,
        }, separators=(",", ":")), flush=True)
        return 0
    except BaseException as exc:
        print(json.dumps({
            "protocol": PROTOCOL, "run_id": RUN_ID, "role": ROLE,
            "result": "FAIL", "check": CHECK, "error_type": type(exc).__name__,
        }, separators=(",", ":")), flush=True)
        return 1
    finally:
        if status is not None:
            status.release_gateway_runtime_lock()
        if callable(arm_alarm):
            arm_alarm(0)


if __name__ == "__main__":
    raise SystemExit(main())
