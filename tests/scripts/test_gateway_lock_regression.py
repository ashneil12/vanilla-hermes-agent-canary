"""Offline safety contracts; the publisher separately runs the real Linux test."""

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import Mock, patch

import pytest


SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts" / "ci"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


driver = load_script("gateway_lock_regression")


@pytest.fixture(autouse=True)
def forbid_real_docker(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("real Docker invocation forbidden in offline tests")

    monkeypatch.setattr(driver.subprocess, "run", forbidden)


@pytest.fixture
def harness():
    value = driver.Harness("/fake/docker", "local-test:exact", "b" * 40, "pass\n")
    value.image_id = "sha256:" + "a" * 64
    value.ids = {"owner": "1" * 64, "reader": "2" * 64}
    return value


def container_row(harness, role):
    return {
        "Id": harness.ids[role], "Name": "/" + harness.names[role],
        "Image": harness.image_id,
        "Config": {
            "User": "10000:10000", "Entrypoint": ["/opt/hermes/.venv/bin/python"],
            "Labels": harness.labels(role),
        },
        "HostConfig": {
            "NetworkMode": "none", "PidMode": "", "Init": False,
            "Privileged": False, "CapAdd": [], "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"], "ReadonlyRootfs": True,
            "Memory": driver.MEMORY_BYTES, "MemorySwap": driver.MEMORY_BYTES,
            "NanoCpus": 250_000_000, "PidsLimit": 16,
            "RestartPolicy": {"Name": "no"},
        },
        "Mounts": [{"Type": "volume", "Name": harness.volume, "Destination": "/opt/data"}],
    }


def fake_daemon(harness, *, changed_role=None, changed_name=False, wrong_labels=False):
    rows = {role: container_row(harness, role) for role in harness.names}
    if changed_role and changed_name:
        rows[changed_role]["Name"] = "/renamed-externally"
    if changed_role and wrong_labels:
        rows[changed_role]["Config"]["Labels"] = {}
    present = set(rows)
    volume_present = True
    calls = []
    harness.attempted_roles = set(rows)
    harness.volume_attempted = True

    def call(args, **kwargs):
        nonlocal volume_present
        calls.append((args, kwargs))
        if args[:2] == ["container", "ls"]:
            value = args[args.index("--filter") + 1]
            if value.startswith("id="):
                return "\n".join(rows[role]["Id"] for role in present if rows[role]["Id"] == value[3:])
            return "\n".join(
                rows[role]["Id"] + " " + rows[role]["Name"].lstrip("/")
                for role in present if "^" + rows[role]["Name"] + "$" == value[5:]
            )
        if args[:2] == ["container", "inspect"]:
            return json.dumps([next(row for role, row in rows.items() if role in present and row["Id"] == args[2])])
        if args[:2] == ["container", "rm"]:
            assert kwargs["mutation"] and args[2] == "--force"
            role = next(role for role in present if rows[role]["Id"] == args[3])
            present.remove(role)
            return args[3]
        if args[:2] == ["volume", "ls"]:
            return harness.volume if volume_present else ""
        if args[:2] == ["volume", "inspect"]:
            return json.dumps([{
                "Name": harness.volume, "Driver": "local", "Labels": harness.labels("state"),
                "Options": driver.VOLUME_OPTIONS,
            }])
        if args[:2] == ["volume", "rm"]:
            assert kwargs["mutation"] and args[2] == harness.volume
            if present:
                raise driver.Failure("volume-in-use")
            volume_present = False
            return harness.volume
        raise AssertionError("unexpected mocked Docker command")

    return call, calls, present


def test_expected_isolation_passes(harness):
    harness.check_isolation(container_row(harness, "owner"))


@pytest.mark.parametrize("key,value", [
    ("NetworkMode", "host"), ("PidMode", "host"), ("Init", True),
    ("Privileged", True), ("CapAdd", ["SYS_ADMIN"]), ("CapDrop", []),
    ("SecurityOpt", []), ("SecurityOpt", ["no-new-privileges:false"]),
    ("ReadonlyRootfs", False), ("Memory", 0), ("MemorySwap", -1),
    ("NanoCpus", 0), ("PidsLimit", 0), ("RestartPolicy", {"Name": "always"}),
])
def test_unsafe_runtime_settings_fail_closed(harness, key, value):
    row = container_row(harness, "owner")
    row["HostConfig"][key] = value
    with pytest.raises(driver.Failure):
        harness.check_isolation(row)


def test_extra_socket_mount_is_rejected(harness):
    row = container_row(harness, "owner")
    row["Mounts"].append({"Type": "bind", "Destination": "/var/run/docker.sock"})
    with pytest.raises(driver.Failure):
        harness.check_isolation(row)


def test_bad_oci_revision_prevents_resource_creation(harness):
    image = {
        "Id": harness.image_id, "Os": "linux",
        "Config": {"Labels": {"org.opencontainers.image.revision": "c" * 40}},
    }
    with patch.object(harness, "parsed", return_value=[image]), patch.object(harness, "call") as call:
        with pytest.raises(driver.Failure, match="revision-mismatch"):
            harness.preflight()
        call.assert_not_called()
    assert not harness.volume_attempted and not harness.attempted_roles


def test_extra_image_volume_prevents_resource_creation(harness):
    image = {
        "Id": harness.image_id, "Os": "linux", "Config": {
            "Labels": {"org.opencontainers.image.revision": harness.revision},
            "Volumes": {"/opt/data": {}, "/unexpected": {}},
        },
    }
    with patch.object(harness, "parsed", return_value=[image]), patch.object(harness, "call") as call:
        with pytest.raises(driver.Failure, match="unexpected-image-anonymous-volumes"):
            harness.preflight()
        call.assert_not_called()
    assert not harness.volume_attempted and not harness.attempted_roles


def test_cleanup_verifies_exact_ids_and_absence(harness):
    call, calls, present = fake_daemon(harness)
    with patch.object(harness, "call", side_effect=call):
        assert harness.cleanup()
    assert not present
    removed = [args[-1] for args, _ in calls if args[:2] == ["container", "rm"]]
    assert set(removed) == set(harness.ids.values())
    assert all(len(value) == 64 for value in removed)


@pytest.mark.parametrize("change", ["name", "labels"])
def test_changed_resource_is_not_removed_or_reported_clean(harness, change):
    call, calls, present = fake_daemon(
        harness, changed_role="owner", changed_name=change == "name", wrong_labels=change == "labels",
    )
    with patch.object(harness, "call", side_effect=call):
        assert not harness.cleanup()
    assert "owner" in present
    assert not any(
        args[:2] == ["container", "rm"] and args[-1] == harness.ids["owner"]
        for args, _ in calls
    )


def test_cli_uses_local_socket_clean_env_and_timeout(harness, monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "tcp://must-not-be-used:2375")
    monkeypatch.setenv("API_KEY", "must-not-be-forwarded")
    with patch.object(driver.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
        harness.call(["image", "inspect", "local:exact"], step="read", timeout=7)
    args, kwargs = run.call_args
    assert args[0][:3] == ["/fake/docker", "--host", "unix:///var/run/docker.sock"]
    assert set(kwargs["env"]) == {"PATH", "LANG"}
    assert kwargs["timeout"] <= 7


def test_mutation_timeout_never_becomes_cleanup_pass(harness):
    with patch.object(driver.subprocess, "run", side_effect=subprocess.TimeoutExpired("hidden", 1)):
        with pytest.raises(driver.Failure):
            harness.call(["container", "start", harness.ids["owner"]], step="start", mutation=True)
    assert harness.uncertain_mutation
    assert not harness.cleanup()


def test_expired_deadline_prevents_command(harness):
    harness.deadline = time.monotonic() - 1
    with patch.object(driver.subprocess, "run") as run:
        with pytest.raises(driver.Failure, match="phase-deadline"):
            harness.call(["image", "inspect", "local:exact"], step="read")
        run.assert_not_called()


def test_fixture_freshness_precedes_private_import_homes(tmp_path):
    with patch.object(sys, "argv", ["worker", "owner", "b" * 32]):
        worker = load_script("gateway_lock_worker")
    # conftest already creates the isolated Hermes home under tmp_path.
    # The Docker fixture itself must still start on a truly empty volume.
    fixture_root = tmp_path / "isolated-test-volume"
    fixture_root.mkdir()
    worker.ROOT = fixture_root
    owner_home = worker.prepare_fixture()
    assert owner_home.name == "import-owner"
    assert (fixture_root / "fixture-ready.json").is_file()
    sentinel = worker.fingerprint(fixture_root / "control" / "sentinel")
    (owner_home / "sessions").mkdir()
    worker.ROLE = "reader"
    reader_home = worker.prepare_fixture()
    assert reader_home.name == "import-reader"
    (reader_home / "logs").mkdir()
    worker.check_other_profile(fixture_root / "control", sentinel)
    worker.ROLE = "owner"
    with pytest.raises(AssertionError, match="fresh-empty-test-volume"):
        worker.prepare_fixture()


def assert_worker_rejects_non_linux_before_platform_calls(tmp_path, capsys):
    with patch.object(sys, "argv", ["worker", "owner", "b" * 32]):
        worker = load_script("gateway_lock_worker")
    worker.ROOT = tmp_path / "must-not-be-created"
    with patch.object(worker.signal, "signal", side_effect=AssertionError("platform signal accessed")) as register:
        assert worker.main() == 1
    register.assert_not_called()
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["result"] == "FAIL" and receipt["check"] == "linux-worker"
    assert not worker.ROOT.exists()


@pytest.mark.macos_only
def test_worker_rejects_native_macos_before_platform_calls(tmp_path, capsys):
    assert_worker_rejects_non_linux_before_platform_calls(tmp_path, capsys)


@pytest.mark.windows_only
def test_worker_rejects_native_windows_before_platform_calls(tmp_path, capsys):
    assert_worker_rejects_non_linux_before_platform_calls(tmp_path, capsys)


@pytest.mark.linux_only
@pytest.mark.parametrize("behavior_ok,cleanup_ok", [(True, True), (False, True), (True, False), (False, False)])
def test_injected_cli_requires_behavior_and_cleanup_without_sibling_read(monkeypatch, behavior_ok, cleanup_ok):
    fake = Mock(run_id="test", image_id="sha256:" + "a" * 64)
    if behavior_ok:
        fake.run.return_value = {"offline": True}
    else:
        fake.run.side_effect = driver.Failure("worker-failed")
    fake.cleanup.return_value = cleanup_ok
    factory = Mock(return_value=fake)
    monkeypatch.setattr(sys, "argv", ["probe", "local:exact", "b" * 40, "--capacity-and-idle-preflight-confirmed"])
    monkeypatch.setattr(driver.shutil, "which", lambda name: "/fake/docker")
    monkeypatch.setattr(driver.signal, "signal", Mock())
    monkeypatch.setattr(driver, "Harness", factory)
    monkeypatch.setattr(driver, "Path", Mock(side_effect=AssertionError("sibling read forbidden")))
    monkeypatch.delattr(driver, "__file__")
    output = io.StringIO()
    with redirect_stdout(output):
        result = driver.main(worker_source="pass\n")
    expected_pass = behavior_ok and cleanup_ok
    assert result == (0 if expected_pass else 1)
    receipt = json.loads(output.getvalue().splitlines()[-1])
    assert receipt["result"] == ("PASS" if expected_pass else "FAIL")
    factory.assert_called_once_with("/fake/docker", "local:exact", "b" * 40, "pass\n")
    fake.cleanup.assert_called_once_with()
