"""hermes-fork: Venice / Surplus / Bankr provider-plugin behaviour (hermes_cli/fork_providers.py).

These replace the old fork edits in agent_init / chat_completion_helpers / conversation_loop /
hermes_cli.models: the logic now rides upstream's public ProviderProfile hooks, so the seam is
"the bundled plugin registers the fork profile classes", and the behaviour is asserted through the
real chat-completions transport.
"""

import pytest

from hermes_cli.fork_providers import (
    VENICE_MODEL_ALIASES,
    SortedCatalogMixin,
    VeniceProfile,
    normalize_venice_model_id,
    sort_discovered_model_ids,
)


# --- seam wiring: bundled plugins register the fork profile classes -------------------------

def test_bundled_provider_plugins_use_fork_profiles():
    from providers import get_provider_profile

    assert isinstance(get_provider_profile("venice"), VeniceProfile)
    assert isinstance(get_provider_profile("surplus"), SortedCatalogMixin)
    assert isinstance(get_provider_profile("bankr"), SortedCatalogMixin)
    # Aliases and wire contract of the three providers stay what Hivra provisions.
    assert get_provider_profile("bankr-gateway").name == "bankr"
    assert get_provider_profile("surplus-intelligence").base_url == "https://www.surplusintelligence.ai/api/inference/v1"
    assert get_provider_profile("venice-ai").env_vars == ("VENICE_API_KEY", "VENICE_BASE_URL")
    for name in ("venice", "surplus", "bankr"):
        profile = get_provider_profile(name)
        assert profile.api_mode == "chat_completions" and profile.auth_type == "api_key"


# --- Venice cross-vendor model remap --------------------------------------------------------

class TestNormalizeVeniceModelId:
    def test_anthropic_openrouter_slug_remaps(self):
        assert normalize_venice_model_id("anthropic/claude-sonnet-4") == ("claude-sonnet-4-6", "anthropic/claude-sonnet-4")

    def test_dotted_vendor_slug_remaps(self):
        assert normalize_venice_model_id("anthropic/claude-sonnet-4.6") == ("claude-sonnet-4-6", "anthropic/claude-sonnet-4.6")

    def test_real_venice_id_is_noop(self):
        assert normalize_venice_model_id("kimi-k2-6") == ("kimi-k2-6", None)

    def test_bare_claude_forms_remap(self):
        assert normalize_venice_model_id("claude-sonnet-4") == ("claude-sonnet-4-6", "claude-sonnet-4")
        assert normalize_venice_model_id("claude-opus-4") == ("claude-opus-4-8", "claude-opus-4")

    def test_cross_vendor_gpt_gemini_kimi(self):
        assert normalize_venice_model_id("openai/gpt-5.5") == ("openai-gpt-55", "openai/gpt-5.5")
        assert normalize_venice_model_id("google/gemini-3-flash-preview")[0] == "gemini-3-flash-preview"
        assert normalize_venice_model_id("moonshotai/kimi-k2.6")[0] == "kimi-k2-6"

    def test_unknown_model_passes_through(self):
        assert normalize_venice_model_id("some-unknown-model") == ("some-unknown-model", None)
        assert normalize_venice_model_id("anthropic/totally-made-up") == ("anthropic/totally-made-up", None)

    def test_empty_and_none(self):
        assert normalize_venice_model_id("") == ("", None)
        assert normalize_venice_model_id(None) == ("", None)

    def test_case_insensitive_lookup(self):
        assert normalize_venice_model_id("Anthropic/Claude-Sonnet-4") == ("claude-sonnet-4-6", "Anthropic/Claude-Sonnet-4")

    def test_alias_targets_are_idempotent(self):
        for target in set(VENICE_MODEL_ALIASES.values()):
            assert normalize_venice_model_id(target) == (target, None)


@pytest.fixture
def transport():
    from agent.transports.chat_completions import ChatCompletionsTransport

    return ChatCompletionsTransport()


def _build(transport, provider, model):
    from providers import get_provider_profile

    profile = get_provider_profile(provider)
    return transport.build_kwargs(
        model=model, messages=[{"role": "user", "content": "hi"}], tools=[],
        provider_profile=profile, provider_name=provider, base_url=profile.base_url,
    )


def test_venice_request_model_is_remapped_on_the_wire(transport):
    assert _build(transport, "venice", "anthropic/claude-sonnet-4")["model"] == "claude-sonnet-4-6"
    assert _build(transport, "venice", "claude-sonnet-4-6")["model"] == "claude-sonnet-4-6"


def test_other_providers_are_never_remapped(transport):
    assert _build(transport, "openrouter", "anthropic/claude-sonnet-4")["model"] == "anthropic/claude-sonnet-4"
    assert _build(transport, "surplus", "claude-sonnet-4")["model"] == "claude-sonnet-4"


def test_venice_character_slug_injected_only_when_configured(transport, monkeypatch):
    import hermes_cli.fork_providers as fp

    monkeypatch.setattr(fp, "configured_venice_character_slug", lambda: "")
    assert "venice_parameters" not in (_build(transport, "venice", "kimi-k2-6").get("extra_body") or {})
    monkeypatch.setattr(fp, "configured_venice_character_slug", lambda: "mentor")
    body = _build(transport, "venice", "kimi-k2-6")["extra_body"]
    assert body["venice_parameters"] == {"character_slug": "mentor"}
    # A non-Venice provider never sees the slug, even when configured.
    assert "venice_parameters" not in (_build(transport, "surplus", "m").get("extra_body") or {})


def test_character_slug_is_read_from_config(tmp_path, monkeypatch):
    from hermes_cli import config as config_module
    from hermes_cli.fork_providers import configured_venice_character_slug

    home = tmp_path / ".hermes"
    home.mkdir()
    (home / "config.yaml").write_text("venice:\n  character_slug: '  mentor '\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))
    config_module._LOAD_CONFIG_CACHE.clear()
    config_module._RAW_CONFIG_CACHE.clear()
    assert configured_venice_character_slug() == "mentor"


# --- family-sorted live catalogs ------------------------------------------------------------

def test_sort_discovered_model_ids_clusters_families():
    ids = ["llama-3.3-70b", "claude-opus-4.6-fast", "gpt-5.5", "Claude-opus-4-8-fast", "claude-haiku-4.5"]
    assert sort_discovered_model_ids(ids) == [
        "claude-haiku-4.5", "Claude-opus-4-8-fast", "claude-opus-4.6-fast", "gpt-5.5", "llama-3.3-70b",
    ]


@pytest.mark.parametrize("provider", ["surplus", "bankr", "venice"])
def test_live_catalog_is_family_sorted(provider, monkeypatch):
    from providers import get_provider_profile
    from providers.base import ProviderProfile

    live = ["zeta-1", "claude-opus-4.6-fast", "Alpha-2", "claude-opus-4-8-fast"]
    monkeypatch.setattr(ProviderProfile, "fetch_models", lambda self, **kw: list(live))
    got = get_provider_profile(provider).fetch_models(api_key="k")
    assert got == sorted(live, key=str.lower)


def test_failed_catalog_fetch_stays_none(monkeypatch):
    from providers import get_provider_profile
    from providers.base import ProviderProfile

    monkeypatch.setattr(ProviderProfile, "fetch_models", lambda self, **kw: None)
    assert get_provider_profile("surplus").fetch_models(api_key="k") is None
