#!/usr/bin/env python3
"""Bounded two-container regression for a disposable local Linux Docker daemon.

The image publisher runs this before registry login or push. Manual use still
requires an operator capacity/idle check; never target customer runtime state.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid


PROTOCOL = "hermes-lock-regression-v1"
LABEL = "io.hermes.test.gateway-lock"
OPERATION_SECONDS = 120
CLEANUP_SECONDS = 60
MEMORY_BYTES = 128 * 1024 * 1024
VOLUME_OPTIONS = {
    "type": "tmpfs", "device": "tmpfs",
    "o": "rw,nosuid,nodev,noexec,size=1048576,uid=10000,gid=10000,mode=0700",
}
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
CONTAINER_ID = re.compile(r"[0-9a-f]{64}\Z")


class Failure(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Failure(message)


def emit(event, **fields):
    print(json.dumps({"event": event, **fields}, separators=(",", ":")), flush=True)


class Harness:
    def __init__(self, docker, image_ref, revision, worker):
        self.docker = docker
        self.image_ref = image_ref
        self.revision = revision
        self.worker = worker
        self.run_id = uuid.uuid4().hex
        self.names = {role: f"hermes-lock-{self.run_id}-{role}" for role in ("owner", "reader")}
        self.volume = f"hermes-lock-{self.run_id}-state"
        self.ids = {}
        self.image_id = None
        self.image_env_names = []
        self.deadline = time.monotonic() + OPERATION_SECONDS
        self.uncertain_mutation = False
        self.volume_attempted = False
        self.attempted_roles = set()

    def call(self, args, *, step, timeout=10, mutation=False):
        left = self.deadline - time.monotonic()
        require(left > 0, "phase-deadline")
        # Explicit local socket and a clean CLI environment avoid a saved
        # remote context or inherited Docker/provider credentials.
        command = [self.docker, "--host", "unix:///var/run/docker.sock", *args]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True,
                timeout=min(timeout, left),
                env={"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            self.uncertain_mutation |= mutation
            raise Failure(step + ":" + type(exc).__name__) from None
        except BaseException:
            self.uncertain_mutation |= mutation
            raise
        require(len(result.stdout) < 512_000 and len(result.stderr) < 512_000, step + ":output-limit")
        if result.returncode != 0:
            raise Failure(step + ":exit-" + str(result.returncode))
        return result.stdout

    def parsed(self, args, *, step):
        try:
            return json.loads(self.call(args, step=step))
        except (ValueError, TypeError):
            raise Failure(step + ":invalid-json") from None

    def labels(self, role):
        return {LABEL: PROTOCOL, LABEL + ".run": self.run_id, LABEL + ".role": role}

    def check_labels(self, payload, role):
        labels = payload or {}
        require(all(labels.get(key) == value for key, value in self.labels(role).items()), "resource-label-mismatch")

    def volume_present(self):
        names = self.call(["volume", "ls", "--format", "{{.Name}}"], step="volume-inventory").splitlines()
        return self.volume in names

    def inspect_volume(self):
        rows = self.parsed(["volume", "inspect", self.volume], step="volume-inspect")
        require(len(rows) == 1, "volume-inspect-count")
        row = rows[0]
        require(row.get("Name") == self.volume and row.get("Driver") == "local", "volume-identity")
        self.check_labels(row.get("Labels"), "state")
        require(row.get("Options") == VOLUME_OPTIONS, "volume-options")
        return row

    def find_container(self, role):
        lines = self.call([
            "container", "ls", "--all", "--no-trunc", "--format", "{{.ID}} {{.Names}}",
            "--filter", "name=^/" + self.names[role] + "$",
        ], step="container-inventory").splitlines()
        matches = [line.split() for line in lines if line.split()[-1:] == [self.names[role]]]
        require(len(matches) <= 1, "ambiguous-container-name")
        if not matches:
            return None
        require(len(matches[0]) == 2 and CONTAINER_ID.fullmatch(matches[0][0]), "container-id-format")
        return self.inspect_container(role, matches[0][0])

    def container_id_present(self, container_id):
        require(CONTAINER_ID.fullmatch(container_id), "container-id-format")
        ids = self.call([
            "container", "ls", "--all", "--no-trunc", "--format", "{{.ID}}",
            "--filter", "id=" + container_id,
        ], step="container-id-inventory").splitlines()
        require(all(CONTAINER_ID.fullmatch(value) for value in ids), "container-inventory-id-format")
        return container_id in ids

    def inspect_container(self, role, container_id):
        require(CONTAINER_ID.fullmatch(container_id), "container-id-format")
        rows = self.parsed(["container", "inspect", container_id], step="container-inspect")
        require(len(rows) == 1, "container-inspect-count")
        row = rows[0]
        require(row.get("Id") == container_id and row.get("Name") == "/" + self.names[role], "container-identity")
        if role in self.ids:
            require(self.ids[role] == container_id, "container-id-changed")
        self.check_labels(row.get("Config", {}).get("Labels"), role)
        require(row.get("Image") == self.image_id, "container-image-changed")
        return row

    def check_isolation(self, row):
        host = row["HostConfig"]
        config = row["Config"]
        require(config.get("User") == "10000:10000", "container-user")
        require(config.get("Entrypoint") == ["/opt/hermes/.venv/bin/python"], "container-entrypoint")
        require(host.get("NetworkMode") == "none", "container-network")
        require(host.get("PidMode") in ("", "private"), "container-pid-mode")
        require(host.get("Init") is False, "container-no-init-wrapper")
        require(not host.get("Privileged") and not host.get("CapAdd"), "container-privileges")
        require("ALL" in host.get("CapDrop", []), "container-cap-drop")
        require(any(value in ("no-new-privileges", "no-new-privileges:true") for value in host.get("SecurityOpt", [])), "container-no-new-privileges")
        require(host.get("ReadonlyRootfs") is True, "container-read-only")
        require(host.get("Memory") == host.get("MemorySwap") == MEMORY_BYTES, "container-memory")
        require(host.get("NanoCpus") == 250_000_000 and host.get("PidsLimit") == 16, "container-cpu-pids")
        require(host.get("RestartPolicy", {}).get("Name") == "no", "container-no-restart")
        mounts = row.get("Mounts", [])
        require(len(mounts) == 1, "no-unexpected-mounts")
        mount = mounts[0]
        require(mount.get("Type") == "volume" and mount.get("Name") == self.volume and mount.get("Destination") == "/opt/data", "owned-test-volume-only")

    def preflight(self):
        rows = self.parsed(["image", "inspect", self.image_ref], step="image-inspect")
        require(len(rows) == 1, "image-inspect-count")
        image = rows[0]
        self.image_id = image.get("Id", "")
        require(IMAGE_ID.fullmatch(self.image_id), "image-id-format")
        require(image.get("Os") == "linux", "linux-image")
        config = image.get("Config") or {}
        require((config.get("Labels") or {}).get("org.opencontainers.image.revision") == self.revision, "image-revision-mismatch")
        require(set((config.get("Volumes") or {})) <= {"/opt/data"}, "unexpected-image-anonymous-volumes")
        self.image_env_names = [value.split("=", 1)[0] for value in config.get("Env", [])]
        require(all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) for key in self.image_env_names), "image-environment-names")
        require(not self.volume_present(), "volume-name-already-exists")
        for role in self.names:
            require(self.find_container(role) is None, "container-name-already-exists")
        emit("preflight", run_id=self.run_id, image_id=self.image_id, expected_revision=self.revision,
             worker_sha256=hashlib.sha256(self.worker.encode()).hexdigest(), volume=self.volume, containers=self.names,
             operation_seconds=OPERATION_SECONDS, cleanup_seconds=CLEANUP_SECONDS)

    def create_volume(self):
        args = ["volume", "create", "--driver", "local"]
        for key, value in self.labels("state").items():
            args += ["--label", key + "=" + value]
        for key, value in VOLUME_OPTIONS.items():
            args += ["--opt", key + "=" + value]
        self.volume_attempted = True
        self.call([*args, self.volume], step="volume-create", mutation=True)
        self.inspect_volume()

    def create_container(self, role):
        args = [
            "container", "create", "--pull=never", "--name", self.names[role],
            "--network", "none", "--init=false", "--user", "10000:10000", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true", "--read-only",
            "--cpus", "0.25", "--memory", str(MEMORY_BYTES), "--memory-swap", str(MEMORY_BYTES),
            "--pids-limit", "16", "--shm-size", "1048576", "--ulimit", "nofile=128:128",
            "--restart", "no", "--no-healthcheck", "--workdir", "/opt/hermes",
            "--log-driver", "json-file", "--log-opt", "max-size=256k", "--log-opt", "max-file=1",
            "--mount", "type=volume,source=" + self.volume + ",target=/opt/data,volume-nocopy",
            "--entrypoint", "/opt/hermes/.venv/bin/python",
        ]
        for key, value in self.labels(role).items():
            args += ["--label", key + "=" + value]
        # Never forward the operator's environment. Blank inherited image
        # settings, except harmless PATH/HOME; all state remains in /opt/data.
        for key in self.image_env_names:
            if key not in ("PATH", "HOME"):
                args += ["--env", key + "="]
        args += ["--env", "HERMES_HOME=/opt/data/control", "--env", "HERMES_DISABLE_LAZY_INSTALLS=1"]
        args += [self.image_id, "-I", "-B", "-u", "-c", self.worker, role, self.run_id]
        self.attempted_roles.add(role)
        container_id = self.call(args, step=role + "-create", timeout=15, mutation=True).strip()
        require(CONTAINER_ID.fullmatch(container_id), "created-container-id")
        self.ids[role] = container_id
        self.check_isolation(self.inspect_container(role, container_id))

    def receipts(self, role):
        output = self.call(["container", "logs", "--tail", "10", self.ids[role]], step=role + "-logs")
        rows = []
        for line in output.splitlines():
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict) and value.get("protocol") == PROTOCOL and value.get("run_id") == self.run_id and value.get("role") == role:
                rows.append(value)
        return rows

    def run(self):
        self.preflight()
        self.create_volume()
        for role in self.names:
            self.create_container(role)
        for role in self.names:
            self.check_isolation(self.inspect_container(role, self.ids[role]))
            self.call(["container", "start", self.ids[role]], step=role + "-start", timeout=15, mutation=True)
        done = set()
        evidence = {}
        while len(done) < 2:
            require(time.monotonic() < self.deadline, "operation-deadline")
            for role in self.names:
                if role in done:
                    continue
                row = self.inspect_container(role, self.ids[role])
                state = row["State"]
                if state.get("Running"):
                    continue
                require(state.get("Status") == "exited", role + ":unexpected-container-state")
                rows = self.receipts(role)
                require(len(rows) == 1, role + ":missing-unique-receipt")
                receipt = rows[0]
                emit("worker", role=role, result=receipt.get("result"), check=receipt.get("check"), error_type=receipt.get("error_type"))
                require(state.get("ExitCode") == 0 and state.get("OOMKilled") is False and receipt.get("result") == "PASS", role + ":worker-failed")
                require(receipt.get("cases") == ["default", "explicit-profile"], role + ":case-coverage")
                evidence[role] = receipt
                done.add(role)
            if len(done) < 2:
                time.sleep(0.2)
        require(evidence["owner"]["namespace"] != evidence["reader"]["namespace"], "namespaces-not-distinct")
        require(evidence["owner"].get("handoff_verified") is True, "owner-handoff-evidence")
        require(all(evidence["reader"].get(key) is True for key in (
            "pid_collision_rejected", "held_files_preserved", "second_acquisition_denied",
            "release_cleanup_reacquisition", "other_profile_preserved",
        )), "reader-behavior-evidence")
        return evidence

    def cleanup(self):
        self.deadline = time.monotonic() + CLEANUP_SECONDS
        errors = []
        for role in self.names:
            if role not in self.attempted_roles:
                continue
            try:
                known_id = self.ids.get(role)
                if known_id is not None and self.container_id_present(known_id):
                    row = self.inspect_container(role, known_id)
                else:
                    row = self.find_container(role)
                if row is not None:
                    # Labels, image, name, and any previously captured ID have
                    # all been checked. Mutation uses only this exact full ID.
                    self.call(["container", "rm", "--force", row["Id"]], step=role + "-remove", mutation=True)
                require(self.find_container(role) is None, role + ":container-remained")
                if known_id is not None:
                    require(not self.container_id_present(known_id), role + ":container-id-remained")
            except Failure as exc:
                errors.append(str(exc))
        if self.volume_attempted:
            try:
                if self.volume_present():
                    self.inspect_volume()
                    self.call(["volume", "rm", self.volume], step="volume-remove", mutation=True)
                require(not self.volume_present(), "volume-remained")
            except Failure as exc:
                errors.append(str(exc))
        if self.uncertain_mutation:
            errors.append("a-mutation-timed-out-or-was-uncertain")
        emit("cleanup", result="PASS" if not errors else "FAIL", run_id=self.run_id,
             containers=self.names, volume=self.volume, errors=errors)
        return not errors


def main(worker_source: str | None = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", help="Already-local image reference; never pulled, then pinned by inspected image ID")
    parser.add_argument("revision", help="Expected full 40-character OCI revision")
    parser.add_argument("--capacity-and-idle-preflight-confirmed", action="store_true", required=True)
    args = parser.parse_args()
    require(sys.platform.startswith("linux"), "Linux-host-required")
    require(re.fullmatch(r"[0-9a-f]{40}", args.revision), "full-revision-required")
    require(args.image and not args.image.startswith("-") and not re.search(r"\s", args.image), "invalid-image-reference")
    docker = shutil.which("docker")
    require(docker is not None, "docker-cli-missing")
    if worker_source is None:
        worker_path = Path(__file__).with_name("gateway_lock_worker.py")
        worker = worker_path.read_text(encoding="utf-8")
    else:
        require(isinstance(worker_source, str), "worker-source-must-be-text")
        worker = worker_source
    ast.parse(worker)
    harness = Harness(docker, args.image, args.revision, worker)
    def interrupted(signum, frame):
        raise Failure("operator-interrupt")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    passed = False
    try:
        evidence = harness.run()
        passed = True
        emit("behavior", result="PASS", run_id=harness.run_id, image_id=harness.image_id,
             expected_revision=args.revision, evidence=evidence)
    except BaseException as exc:
        # Never echo Docker stderr, environment values, or arbitrary tracebacks.
        emit("behavior", result="FAIL", run_id=harness.run_id,
             reason=str(exc) if isinstance(exc, Failure) else type(exc).__name__)
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        cleaned = harness.cleanup()
    emit("result", result="PASS" if passed and cleaned else "FAIL", run_id=harness.run_id)
    return 0 if passed and cleaned else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Failure as exc:
        emit("preflight", result="FAIL", reason=str(exc))
        raise SystemExit(1)
