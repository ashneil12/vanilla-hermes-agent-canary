"""Dashboard health probes against the real authenticated gateway handlers."""

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer


GATEWAY_KEY = "test-gateway-key-not-a-real-secret"
OTHER_KEY = "test-other-key-not-a-real-secret"


@pytest.fixture
def probe_modules(monkeypatch):
    # Import the real modules only after conftest has isolated HERMES_HOME.
    from gateway import run, status
    from gateway.platforms import api_server
    from hermes_cli import web_server

    monkeypatch.setattr(status, "read_runtime_status", lambda: {
        "gateway_state": "running",
        "active_agents": 2,
        "platforms": {"api_server": {"state": "connected"}},
    })
    monkeypatch.setattr(run, "_resolve_gateway_model", lambda: "test/model")
    monkeypatch.setattr(api_server, "collect_runtime_readiness", lambda **_: {
        "status": "ok",
    })
    monkeypatch.setattr(web_server, "_GATEWAY_HEALTH_TIMEOUT", 0.5)
    return web_server, api_server


def _write_key(home: Path, key: str, filename: str = "config.yaml") -> None:
    # JSON is also valid YAML. Exercise the actual config/legacy readers.
    (home / filename).write_text(json.dumps({
        "platforms": {"api_server": {"enabled": True, "extra": {"key": key}}},
    }), encoding="utf-8")


@asynccontextmanager
async def _gateway_server(api_server, requests, *, detail_gate=None, redirect=None):
    from gateway.config import PlatformConfig

    adapter = api_server.APIServerAdapter(
        PlatformConfig(enabled=True, extra={"key": GATEWAY_KEY}),
    )

    async def detailed(request):
        record = {
            "path": request.path,
            "authorization": request.headers.get("Authorization"),
            "status": None,
        }
        requests.append(record)
        if detail_gate is not None:
            await detail_gate.wait()
        if redirect is not None:
            location, code = redirect
            response = web.Response(status=code, headers={"Location": location})
        else:
            response = await adapter._handle_health_detailed(request)
        record["status"] = response.status
        return response

    async def basic(request):
        response = await adapter._handle_health(request)
        requests.append({
            "path": request.path,
            "authorization": request.headers.get("Authorization"),
            "status": response.status,
        })
        return response

    app = web.Application()
    app.router.add_get("/health/detailed", detailed)
    app.router.add_get("/health", basic)
    async with TestServer(app, host="127.0.0.1") as server:
        yield str(server.make_url("/")).rstrip("/")


def _assert_detailed_result(result):
    alive, body = result
    assert alive is True
    assert body["gateway_state"] == "running"
    assert body["active_agents"] == 2
    assert body["gateway_busy"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", ["", "/health", "/health/detailed"])
async def test_probe_authenticates_detailed_health(probe_modules, monkeypatch, suffix):
    ws, api_server = probe_modules
    monkeypatch.setenv("API_SERVER_KEY", GATEWAY_KEY)
    requests = []
    async with _gateway_server(api_server, requests) as base:
        monkeypatch.setattr(ws, "_GATEWAY_HEALTH_URL", base + suffix)
        result = await asyncio.to_thread(ws._probe_gateway_health)

    _assert_detailed_result(result)
    assert requests == [{
        "path": "/health/detailed",
        "authorization": f"Bearer {GATEWAY_KEY}",
        "status": 200,
    }]


@pytest.mark.asyncio
@pytest.mark.parametrize("key_source", ["environment", "config.yaml", "gateway.json"])
async def test_probe_uses_gateway_config_key_precedence(
    probe_modules, monkeypatch, key_source,
):
    from hermes_constants import get_process_hermes_home

    ws, api_server = probe_modules
    home = get_process_hermes_home()
    _write_key(home, GATEWAY_KEY if key_source == "gateway.json" else OTHER_KEY,
               "gateway.json")
    if key_source != "gateway.json":
        _write_key(home, GATEWAY_KEY if key_source == "config.yaml" else OTHER_KEY)
    if key_source == "environment":
        monkeypatch.setenv("API_SERVER_KEY", GATEWAY_KEY)

    requests = []
    async with _gateway_server(api_server, requests) as base:
        monkeypatch.setattr(ws, "_GATEWAY_HEALTH_URL", base)
        result = await asyncio.to_thread(ws._probe_gateway_health)

    _assert_detailed_result(result)
    assert len(requests) == 1
    assert requests[0]["authorization"] == f"Bearer {GATEWAY_KEY}"


@pytest.mark.asyncio
@pytest.mark.parametrize("key", [None, OTHER_KEY])
async def test_wrong_or_missing_gateway_key_preserves_auth_and_basic_fallback(
    probe_modules, monkeypatch, caplog, key,
):
    ws, api_server = probe_modules
    if key is not None:
        monkeypatch.setenv("API_SERVER_KEY", key)
    # These are deliberately valid for the server, but are NOT gateway keys.
    monkeypatch.setenv("HERMES_DASHBOARD_SESSION_TOKEN", GATEWAY_KEY)
    monkeypatch.setenv("OPENAI_API_KEY", GATEWAY_KEY)
    requests = []
    async with _gateway_server(api_server, requests) as base:
        monkeypatch.setattr(ws, "_GATEWAY_HEALTH_URL", base)
        alive, body = await asyncio.to_thread(ws._probe_gateway_health)

    assert alive is True
    assert body["status"] == "ok"
    assert "gateway_state" not in body
    assert requests == [
        {"path": "/health/detailed",
         "authorization": f"Bearer {key}" if key else None, "status": 401},
        {"path": "/health", "authorization": None, "status": 200},
    ]
    assert GATEWAY_KEY not in caplog.text
    assert OTHER_KEY not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("process_key_source", ["environment", "config.yaml", "missing"])
async def test_ui_profile_scope_cannot_change_process_listener_credentials(
    probe_modules, monkeypatch, tmp_path, process_key_source,
):
    from agent.secret_scope import (
        current_secret_scope, reset_secret_scope, set_secret_scope,
    )
    from hermes_constants import (
        get_hermes_home, get_process_hermes_home,
        reset_hermes_home_override, set_hermes_home_override,
    )

    ws, api_server = probe_modules
    if process_key_source == "environment":
        monkeypatch.setenv("API_SERVER_KEY", GATEWAY_KEY)
    elif process_key_source == "config.yaml":
        _write_key(get_process_hermes_home(), GATEWAY_KEY)
    ui_home = tmp_path / "selected-ui-profile"
    ui_home.mkdir()
    # The missing-key case must fail closed even when the UI scope happens to
    # hold a key that the process listener would accept.
    ui_key = GATEWAY_KEY if process_key_source == "missing" else OTHER_KEY
    _write_key(ui_home, ui_key)
    ui_secrets = {"API_SERVER_KEY": ui_key}

    def probe_with_ui_scope():
        home_token = set_hermes_home_override(ui_home)
        secret_token = set_secret_scope(ui_secrets)
        try:
            result = ws._probe_gateway_health()
            # The resolver must restore both contexts in the caller's thread.
            assert get_hermes_home() == ui_home
            assert current_secret_scope() is ui_secrets
            return result
        finally:
            reset_secret_scope(secret_token)
            reset_hermes_home_override(home_token)

    requests = []
    async with _gateway_server(api_server, requests) as base:
        monkeypatch.setattr(ws, "_GATEWAY_HEALTH_URL", base)
        result = await asyncio.to_thread(probe_with_ui_scope)

    if process_key_source == "missing":
        assert result[0] is True
        assert "gateway_state" not in result[1]
        assert requests[0]["authorization"] is None
        assert requests[0]["status"] == 401
    else:
        _assert_detailed_result(result)
        assert len(requests) == 1
        assert requests[0]["authorization"] == f"Bearer {GATEWAY_KEY}"


@pytest.mark.asyncio
async def test_process_key_fast_path_does_not_load_platform_config(
    probe_modules, monkeypatch,
):
    from gateway import config

    ws, api_server = probe_modules
    monkeypatch.setenv("API_SERVER_KEY", GATEWAY_KEY)

    def unexpected_config_load():
        pytest.fail("Normal health polls must not rerun legacy config bridges")

    monkeypatch.setattr(config, "load_gateway_config", unexpected_config_load)
    requests = []
    async with _gateway_server(api_server, requests) as base:
        monkeypatch.setattr(ws, "_GATEWAY_HEALTH_URL", base)
        result = await asyncio.to_thread(ws._probe_gateway_health)

    _assert_detailed_result(result)
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("weak_key", ["", "short"])
async def test_unusable_process_key_does_not_shadow_config_key(
    probe_modules, monkeypatch, weak_key,
):
    from hermes_constants import get_process_hermes_home

    ws, api_server = probe_modules
    monkeypatch.setenv("API_SERVER_KEY", weak_key)
    _write_key(get_process_hermes_home(), GATEWAY_KEY)
    requests = []
    async with _gateway_server(api_server, requests) as base:
        monkeypatch.setattr(ws, "_GATEWAY_HEALTH_URL", base)
        result = await asyncio.to_thread(ws._probe_gateway_health)

    _assert_detailed_result(result)
    assert len(requests) == 1
    assert requests[0]["authorization"] == f"Bearer {GATEWAY_KEY}"


@pytest.mark.asyncio
async def test_config_failure_restores_contexts_and_preserves_basic_fallback(
    probe_modules, monkeypatch, tmp_path, caplog,
):
    from agent.secret_scope import (
        current_secret_scope, reset_secret_scope, set_secret_scope,
    )
    from gateway import config
    from hermes_constants import (
        get_hermes_home, get_process_hermes_home,
        reset_hermes_home_override, set_hermes_home_override,
    )

    ws, api_server = probe_modules
    process_home = get_process_hermes_home()
    ui_home = tmp_path / "selected-ui-profile"
    ui_home.mkdir()
    ui_secrets = {"API_SERVER_KEY": OTHER_KEY}
    observed_contexts = []

    def fail_config_load():
        observed_contexts.append((get_hermes_home(), current_secret_scope()))
        # Even a credential-bearing exception must not reach logs or the wire.
        raise RuntimeError(GATEWAY_KEY)

    monkeypatch.setattr(config, "load_gateway_config", fail_config_load)

    def probe_with_ui_scope():
        home_token = set_hermes_home_override(ui_home)
        secret_token = set_secret_scope(ui_secrets)
        try:
            result = ws._probe_gateway_health()
            assert get_hermes_home() == ui_home
            assert current_secret_scope() is ui_secrets
            return result
        finally:
            reset_secret_scope(secret_token)
            reset_hermes_home_override(home_token)

    requests = []
    async with _gateway_server(api_server, requests) as base:
        monkeypatch.setattr(ws, "_GATEWAY_HEALTH_URL", base)
        alive, body = await asyncio.to_thread(probe_with_ui_scope)

    assert alive is True
    assert "gateway_state" not in body
    assert observed_contexts == [(process_home, None)]
    assert requests == [{"path": "/health", "authorization": None, "status": 200}]
    assert GATEWAY_KEY not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("redirect_code", [301, 302, 303, 307, 308])
async def test_gateway_key_is_not_forwarded_to_redirect_origin(
    probe_modules, monkeypatch, redirect_code,
):
    ws, api_server = probe_modules
    monkeypatch.setenv("API_SERVER_KEY", GATEWAY_KEY)
    destination_requests = []
    original_requests = []
    async with _gateway_server(api_server, destination_requests) as destination:
        async with _gateway_server(
            api_server, original_requests,
            redirect=(destination + "/health/detailed", redirect_code),
        ) as base:
            monkeypatch.setattr(ws, "_GATEWAY_HEALTH_URL", base)
            alive, body = await asyncio.to_thread(ws._probe_gateway_health)

    assert alive is True
    assert "gateway_state" not in body
    assert original_requests == [
        {"path": "/health/detailed", "authorization": f"Bearer {GATEWAY_KEY}",
         "status": redirect_code},
        {"path": "/health", "authorization": None, "status": 200},
    ]
    # Even an otherwise-valid key must not cross origins. The real destination
    # handler still rejects the request, then the probe uses its basic fallback.
    assert destination_requests == [
        {"path": "/health/detailed", "authorization": None, "status": 401},
    ]


@pytest.mark.asyncio
async def test_detailed_timeout_still_uses_unauthenticated_basic_health(
    probe_modules, monkeypatch,
):
    ws, api_server = probe_modules
    monkeypatch.setenv("API_SERVER_KEY", GATEWAY_KEY)
    monkeypatch.setattr(ws, "_GATEWAY_HEALTH_TIMEOUT", 0.05)
    requests = []
    gate = asyncio.Event()
    async with _gateway_server(api_server, requests, detail_gate=gate) as base:
        monkeypatch.setattr(ws, "_GATEWAY_HEALTH_URL", base)
        try:
            alive, body = await asyncio.wait_for(
                asyncio.to_thread(ws._probe_gateway_health), timeout=2,
            )
        finally:
            gate.set()

    assert alive is True
    assert "gateway_state" not in body
    assert [request["path"] for request in requests] == ["/health/detailed", "/health"]
    assert requests[0]["authorization"] == f"Bearer {GATEWAY_KEY}"
    assert requests[1]["authorization"] is None
