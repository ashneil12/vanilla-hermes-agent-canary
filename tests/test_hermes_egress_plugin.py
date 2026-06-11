"""Tests for the HermesOS egress-probe dashboard plugin (plugins/hermes-egress).

The plugin is loaded dynamically by the dashboard plugin loader (the dir name
contains a hyphen, so it is not importable as a package); these tests load the
module the same way and pin the public contract the Hermesdeploy egress sweep
depends on.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_API_PATH = (
    Path(__file__).resolve().parents[1]
    / "plugins"
    / "hermes-egress"
    / "dashboard"
    / "plugin_api.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("hermes_egress_plugin_api", _API_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_exposes_router_with_check_route():
    mod = _load_module()
    assert getattr(mod, "router", None) is not None
    paths = {getattr(r, "path", None) for r in mod.router.routes}
    assert "/check" in paths


def test_resolve_targets_enforces_allowlist():
    mod = _load_module()
    # Unknown hosts are ignored; with none allowed we fall back to the defaults.
    assert mod._resolve_targets("evil.example.com,10.0.0.1") == list(mod._DEFAULT_TARGETS)
    # An allowed host passes through verbatim.
    assert mod._resolve_targets("api.openai.com") == ["api.openai.com"]
    # Empty / garbage query falls back to the default probe set.
    assert mod._resolve_targets("") == list(mod._DEFAULT_TARGETS)
    assert mod._resolve_targets("   ,, ") == list(mod._DEFAULT_TARGETS)


def test_probe_failure_reported_in_band(monkeypatch):
    mod = _load_module()
    import socket as _socket

    def _boom(*_a, **_k):
        raise _socket.gaierror("Name or service not known")

    # Force a DNS failure deterministically — no real network in the test.
    monkeypatch.setattr(mod.socket, "getaddrinfo", _boom)
    result = mod._probe_one_target("api.openai.com")
    assert result["ok"] is False
    assert result["errorClass"] == "gaierror"
    assert "durationMs" in result
