"""hermes-fork: bankr-env-bridge + hivra-core prompt plugin (seam wiring + behaviour).

The Hivra dashboard provisions a Bankr wallet by writing a ``bankr:`` section into
config.yaml; ``hermes_cli.fork_bankr`` bridges it to ``BANKR_*`` env vars and the bundled
``plugins/hivra-core`` plugin turns it into system-prompt guidance. Everything must stay inert
when no wallet is provisioned.
"""

import os

import pytest

_BANKR_ENV_KEYS = (
    "BANKR_AGENT_WALLET_ADDRESS",
    "BANKR_AGENT_API_KEY",
    "BANKR_AGENT_WALLET_ID",
    "BANKR_AGENT_WITHDRAWAL_DESTINATION",
    "BANKR_API_KEY",
    "BANKR_WALLET_ADDRESS",
)

_WALLET_YAML = """
bankr:
  walletAddress: "0x000000000000000000000000000000000000ba5e"
  apiKey: "bk_agent_cleartext_secret"
  walletId: "wlt_123"
  withdrawalDestination: "0x000000000000000000000000000000000000feed"
"""


@pytest.fixture(autouse=True)
def _clean_bankr_env(monkeypatch):
    for key in _BANKR_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _clear_config_caches(config_module):
    config_module._LOAD_CONFIG_CACHE.clear()
    config_module._RAW_CONFIG_CACHE.clear()
    config_module._LAST_EXPANDED_CONFIG_BY_PATH.clear()


def _home_with_config(tmp_path, monkeypatch, yaml_text):
    home = tmp_path / ".hermes"
    home.mkdir()
    (home / "config.yaml").write_text(yaml_text, encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))
    from hermes_cli import config as config_module

    _clear_config_caches(config_module)
    return config_module


def _assert_wallet_env():
    assert os.environ["BANKR_AGENT_WALLET_ADDRESS"] == "0x000000000000000000000000000000000000ba5e"
    assert os.environ["BANKR_AGENT_API_KEY"] == "bk_agent_cleartext_secret"
    assert os.environ["BANKR_AGENT_WALLET_ID"] == "wlt_123"
    assert os.environ["BANKR_AGENT_WITHDRAWAL_DESTINATION"] == "0x000000000000000000000000000000000000feed"
    assert os.environ["BANKR_API_KEY"] == "bk_agent_cleartext_secret"
    assert os.environ["BANKR_WALLET_ADDRESS"] == "0x000000000000000000000000000000000000ba5e"


def test_load_config_exports_bankr_wallet_environment_aliases(tmp_path, monkeypatch):
    config_module = _home_with_config(tmp_path, monkeypatch, _WALLET_YAML)
    config_module.load_config()
    _assert_wallet_env()


def test_load_config_readonly_exports_bankr_environment(tmp_path, monkeypatch):
    config_module = _home_with_config(tmp_path, monkeypatch, _WALLET_YAML)
    config_module.load_config_readonly()
    _assert_wallet_env()


def test_cached_load_reexports_bankr_environment(tmp_path, monkeypatch):
    config_module = _home_with_config(tmp_path, monkeypatch, _WALLET_YAML)
    config_module.load_config()
    for key in _BANKR_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    config_module.load_config()  # cache hit must still re-export
    _assert_wallet_env()


def test_save_config_then_load_exports_bankr_environment(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    from hermes_cli import config as config_module

    _clear_config_caches(config_module)
    config_module.save_config({"bankr": {"walletAddress": "0x000000000000000000000000000000000000f00d",
                                         "apiKey": "bk_saved_secret"}})
    config_module.load_config()
    assert os.environ["BANKR_API_KEY"] == "bk_saved_secret"
    assert os.environ["BANKR_WALLET_ADDRESS"] == "0x000000000000000000000000000000000000f00d"


def test_no_bankr_section_is_a_noop(tmp_path, monkeypatch):
    config_module = _home_with_config(tmp_path, monkeypatch, "model:\n  default: x\n")
    config_module.load_config()
    assert not any(k in os.environ for k in _BANKR_ENV_KEYS)


def test_blank_and_non_string_values_are_skipped():
    from hermes_cli.fork_bankr import apply_bankr_env_from_config

    apply_bankr_env_from_config({"bankr": {"walletAddress": "   ", "apiKey": 123, "walletId": None}})
    assert not any(k in os.environ for k in _BANKR_ENV_KEYS)
    apply_bankr_env_from_config({"bankr": "not-a-dict"})
    apply_bankr_env_from_config({})


def test_wallet_prompt_is_empty_without_wallet_env():
    from hermes_cli.fork_bankr import build_bankr_wallet_prompt

    assert build_bankr_wallet_prompt() == ""


def test_wallet_prompt_names_address_but_never_the_key(monkeypatch):
    from hermes_cli.fork_bankr import build_bankr_wallet_prompt

    monkeypatch.setenv("BANKR_API_KEY", "bk_super_secret")
    monkeypatch.setenv("BANKR_WALLET_ADDRESS", "0xabc")
    prompt = build_bankr_wallet_prompt()
    assert "Bankr wallet" in prompt and "0xabc" in prompt
    assert "bk_super_secret" not in prompt


def test_hivra_core_plugin_registers_prompt_sections(monkeypatch):
    """Wiring: the bundled plugin auto-loads and its wallet section renders only with wallet env."""
    from hermes_cli import plugins

    monkeypatch.setenv("BANKR_API_KEY", "bk_secret")
    monkeypatch.setenv("BANKR_WALLET_ADDRESS", "0xdeadbeef")
    manager = plugins.PluginManager()
    manager.discover_and_load()
    rendered = {s.id: s.content for s in manager.render_system_prompt_sections({})}
    assert "hivra-bankr-wallet" in rendered
    assert "0xdeadbeef" in rendered["hivra-bankr-wallet"]
    assert "bk_secret" not in rendered["hivra-bankr-wallet"]

    monkeypatch.delenv("BANKR_API_KEY")
    monkeypatch.delenv("BANKR_WALLET_ADDRESS")
    rendered = {s.id for s in manager.render_system_prompt_sections({})}
    assert "hivra-bankr-wallet" not in rendered


def test_media_guidance_follows_hosted_media_tool_availability(monkeypatch):
    """hivra-core's media section is empty (skipped by core) unless a hosted media tool is available."""
    import importlib.util
    from pathlib import Path

    from tools.registry import registry

    spec = importlib.util.spec_from_file_location(
        "hivra_core_plugin_under_test", Path(__file__).resolve().parents[2] / "plugins" / "hivra-core" / "__init__.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    monkeypatch.setattr(registry, "get_definitions", lambda names, quiet=False: [])
    assert mod._media_guidance({}) == ""
    monkeypatch.setattr(registry, "get_definitions", lambda names, quiet=False: [{"function": {"name": "audio_generate"}}])
    assert "audio_generate" in mod._media_guidance({})
