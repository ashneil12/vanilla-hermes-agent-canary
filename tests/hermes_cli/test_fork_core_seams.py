"""hermes-fork: living manifest for the provider/core seams, plus the brick-protection contract.

The fork keeps these edits in upstream-owned files (each marked ``hermes-fork: <seam>``); if an
upstream merge silently drops one, this file fails instead of a customer box.

Brick protection (a keyless provider written into config.yaml aborts every future session with
"Provider X is set in config.yaml but no API key was found") is NOT a fork edit any more:
upstream's switch_model rejects a switch to a provider with no resolvable credentials, and its
config.set handler rescues a session whose agent failed to build. The contract tests below pin
that behaviour so an upstream change that removes it is noticed (and the fork guard re-added).
"""

from pathlib import Path

import pytest

import hermes_cli.model_switch as ms

_ROOT = Path(__file__).resolve().parents[2]

# seam name -> upstream-owned files that must carry the marker.
_SEAMS = {
    "bankr-env-bridge": ["hermes_cli/config.py"],
    "install-dir-home-guard": ["hermes_constants.py", "hermes_cli/env_loader.py"],
}


@pytest.mark.parametrize("seam,rel", [(s, f) for s, files in _SEAMS.items() for f in files])
def test_seam_marker_present(seam, rel):
    assert f"hermes-fork: {seam}" in (_ROOT / rel).read_text(encoding="utf-8"), f"{rel} lost seam {seam!r}"


def test_fork_only_modules_exist():
    for rel in ("hermes_cli/fork_bankr.py", "hermes_cli/fork_providers.py", "hermes_fork_home.py",
                "plugins/hivra-core/plugin.yaml", "plugins/hivra-core/__init__.py"):
        assert (_ROOT / rel).is_file(), rel


# --- brick protection contract (upstream-native) -------------------------------------------

_SURPLUS_URL = "https://www.surplusintelligence.ai/api/inference/v1"


@pytest.fixture
def surplus_only_box(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("SURPLUS_API_KEY", "inf_test_12345678")
    for var in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def _switch(**overrides):
    kwargs = dict(
        raw_input="gpt-5.5-pro", current_provider="surplus", current_model="claude-haiku-4.5",
        current_base_url=_SURPLUS_URL, current_api_key="inf_test_12345678", is_global=True,
    )
    kwargs.update(overrides)
    return ms.switch_model(**kwargs)


def test_switch_to_provider_without_a_key_is_rejected(surplus_only_box):
    result = _switch(explicit_provider="openai-api")
    assert not result.success
    assert result.target_provider == "openai-api"
    assert "no API key" in result.error_message


def test_bare_model_routed_to_keyless_provider_is_rejected(surplus_only_box, monkeypatch):
    monkeypatch.setattr(ms, "resolve_alias", lambda *a, **k: None)
    monkeypatch.setattr("hermes_cli.models.detect_provider_for_model", lambda model, current: ("openai-api", model))
    result = _switch(explicit_provider="", is_global=False)
    assert not result.success
    assert result.target_provider == "openai-api"


def test_repick_on_current_provider_still_works(surplus_only_box, monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.models_validate.validate_requested_model",
        lambda *a, **kw: {"accepted": True, "persist": True, "recognized": True, "message": None},
    )
    result = _switch(raw_input="some-surplus-model", explicit_provider="")
    assert result.success
    assert result.target_provider == "surplus"


def test_failed_agent_build_has_a_model_switch_rescue():
    """Upstream's config.set(model) path re-arms a failed agent build after switching away from the
    broken provider (replaces the fork's _switch_model_on_dead_session)."""
    from tui_gateway import methods_config_set, model_switch

    assert hasattr(model_switch, "_restart_completed_failed_agent_build")
    src = Path(methods_config_set.__file__).read_text(encoding="utf-8")
    assert "_restart_completed_failed_agent_build" in src and "failed_agent_init" in src
