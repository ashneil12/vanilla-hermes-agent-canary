"""Focused tests for EvoLink provider profile wiring."""

from __future__ import annotations

import pytest

from hermes_cli.auth import (
    PROVIDER_REGISTRY,
    resolve_api_key_provider_credentials,
    resolve_provider,
)
from hermes_cli.models import (
    CANONICAL_PROVIDERS,
    _PROVIDER_LABELS,
    normalize_provider,
    provider_model_ids,
)


_OTHER_PROVIDER_KEYS = (
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "DEEPSEEK_API_KEY",
    "GMI_API_KEY",
    "GMI_BASE_URL",
)


@pytest.fixture(autouse=True)
def _clear_provider_env(monkeypatch):
    for key in _OTHER_PROVIDER_KEYS + ("EVOLINK_API_KEY", "EVOLINK_BASE_URL"):
        monkeypatch.delenv(key, raising=False)


class TestEvoLinkProviderProfile:
    def test_registry_entry(self):
        assert "evolink" in PROVIDER_REGISTRY
        cfg = PROVIDER_REGISTRY["evolink"]
        assert cfg.name == "EvoLink"
        assert cfg.auth_type == "api_key"
        assert cfg.inference_base_url == "https://direct.evolink.ai/v1"
        assert cfg.api_key_env_vars == ("EVOLINK_API_KEY",)
        assert cfg.base_url_env_var == "EVOLINK_BASE_URL"

    @pytest.mark.parametrize("alias", ["evolink", "evo-link", "evolink-ai"])
    def test_alias_resolves(self, alias, monkeypatch):
        monkeypatch.setenv("EVOLINK_API_KEY", "evl-test-key")
        assert resolve_provider(alias) == "evolink"
        assert normalize_provider(alias) == "evolink"

    def test_credentials_default_base_url(self, monkeypatch):
        monkeypatch.setenv("EVOLINK_API_KEY", "evl-test-key")
        creds = resolve_api_key_provider_credentials("evolink")
        assert creds["api_key"] == "evl-test-key"
        assert creds["base_url"] == "https://direct.evolink.ai/v1"

    def test_credentials_allow_base_url_override(self, monkeypatch):
        monkeypatch.setenv("EVOLINK_API_KEY", "evl-test-key")
        monkeypatch.setenv("EVOLINK_BASE_URL", "https://proxy.example.test/v1")
        creds = resolve_api_key_provider_credentials("evolink")
        assert creds["base_url"] == "https://proxy.example.test/v1"


class TestEvoLinkModelCatalog:
    def test_provider_model_ids_uses_fallback_models_without_key(self):
        assert provider_model_ids("evolink") == [
            "gpt-5.2",
            "gpt-5.1",
            "gemini-3.1-flash-lite-preview",
            "deepseek-v4-flash",
        ]

    def test_provider_model_ids_prefers_live_models(self, monkeypatch):
        from providers import get_provider_profile

        profile = get_provider_profile("evolink")
        assert profile is not None
        monkeypatch.setenv("EVOLINK_API_KEY", "evl-test-key")
        monkeypatch.setattr(profile, "fetch_models", lambda api_key: ["gpt-5.2", "custom-live-model"])

        assert set(provider_model_ids("evolink")) == {"gpt-5.2", "custom-live-model"}

    def test_canonical_provider_entry_and_label(self):
        slugs = [p.slug for p in CANONICAL_PROVIDERS]
        assert "evolink" in slugs
        assert _PROVIDER_LABELS["evolink"] == "EvoLink"


class TestEvoLinkProviderResolution:
    def test_provider_overlay_exists(self):
        from hermes_cli.providers import HERMES_OVERLAYS, get_provider

        assert "evolink" in HERMES_OVERLAYS
        overlay = HERMES_OVERLAYS["evolink"]
        assert overlay.transport == "openai_chat"
        assert overlay.extra_env_vars == ("EVOLINK_API_KEY",)
        assert overlay.base_url_override == "https://direct.evolink.ai/v1"
        assert overlay.base_url_env_var == "EVOLINK_BASE_URL"

        provider = get_provider("evolink")
        assert provider is not None
        assert provider.base_url == "https://direct.evolink.ai/v1"
        assert provider.api_key_env_vars == ("EVOLINK_API_KEY",)

    def test_url_to_provider_mapping(self):
        from agent.model_metadata import _URL_TO_PROVIDER

        assert _URL_TO_PROVIDER.get("direct.evolink.ai") == "evolink"
