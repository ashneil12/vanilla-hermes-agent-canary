"""Hivra (hosted Hermes) dashboard seams.

Guards both what the fork still serves (``/api/hivra/config``, mounted from the one marked line in
``web_server.py``) and the upstream behaviours that REPLACED old fork patches, so a future upstream
sync cannot silently lose them (see ``.hermesos/WEBCHAT_SEAMS.md``).
"""

import pytest

from hermes_cli import web_server
from hermes_cli.web_routers import files as files_routes
from hermes_cli.web_routers import fork_hivra

pytest.importorskip("starlette.testclient")
from starlette.testclient import TestClient


@pytest.fixture
def client():
    previous = getattr(web_server.app.state, "auth_required", None)
    web_server.app.state.auth_required = False
    test_client = TestClient(web_server.app)
    test_client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
    try:
        yield test_client
    finally:
        if previous is None:
            try:
                delattr(web_server.app.state, "auth_required")
            except AttributeError:
                pass
        else:
            web_server.app.state.auth_required = previous


def test_fork_router_is_mounted_by_web_server():
    paths = {getattr(route, "path", None) for route in web_server.app.routes}

    assert "/api/hivra/config" in paths


def test_config_exposes_the_control_plane_dashboard_origin(client, monkeypatch):
    monkeypatch.setenv("HERMES_DASHBOARD_URL", "  https://hivra.cloud  ")

    assert client.get("/api/hivra/config").json() == {"dashboard_url": "https://hivra.cloud"}


@pytest.mark.parametrize("raw", ["", "   "])
def test_config_dashboard_url_is_null_when_unset(client, monkeypatch, raw):
    monkeypatch.setenv("HERMES_DASHBOARD_URL", raw)
    assert client.get("/api/hivra/config").json() == {"dashboard_url": None}

    monkeypatch.delenv("HERMES_DASHBOARD_URL")
    assert fork_hivra.dashboard_url() is None


def test_config_requires_the_dashboard_session(client):
    # Not a public path: a client with no token / cookie is refused (the gate is on in prod).
    web_server.app.state.auth_required = True
    anonymous = TestClient(web_server.app)

    assert anonymous.get("/api/hivra/config").status_code == 401


def test_default_cwd_follows_config_terminal_cwd_so_hosted_boxes_need_no_code_patch(monkeypatch, tmp_path):
    """Replaces the old ``_fs_default_cwd`` /workspace-first hunk: the Hivra control plane writes
    ``terminal.cwd: /workspace`` to the box's config.yaml and the file tree opens there.

    NOTE: ``TERMINAL_CWD`` alone is NOT enough. ``load_config()`` merges ``terminal.cwd: "."``
    from DEFAULT_CONFIG and ``_fs_default_cwd`` reads config before the env var, so the "." wins
    and the dashboard falls back to its own launch dir (``/opt/hermes`` in the image)."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.delenv("TERMINAL_CWD", raising=False)
    monkeypatch.setattr(files_routes, "load_config", lambda: {"terminal": {"cwd": str(workspace)}})

    assert files_routes._fs_default_cwd() == str(workspace.resolve())


def test_switching_to_a_byok_provider_adopts_its_own_endpoint(monkeypatch, tmp_path):
    """Replaces ``_provider_profile_base_url``: upstream's canonical ``switch_model`` resolves the
    provider profile's endpoint, so a Surplus pick can never send its key to the previous host."""
    from hermes_cli.model_switch import model_selection_config_updates, switch_model

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("SURPLUS_API_KEY", "inf_test")
    result = switch_model(
        "claude-opus-4.6", current_provider="openrouter", current_model="x/y", explicit_provider="surplus"
    )

    assert result.success, result.error_message
    assert result.base_url == "https://www.surplusintelligence.ai/api/inference/v1"
    updates = model_selection_config_updates(
        result, {"provider": "openrouter", "base_url": "https://openrouter.ai/api/v1"}
    )
    assert updates["provider"] == "surplus"
    assert updates["base_url"] == "https://www.surplusintelligence.ai/api/inference/v1"
