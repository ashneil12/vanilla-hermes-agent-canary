"""Tests for Surplus Intelligence provider support.

Surplus Intelligence is a price-competitive, OpenAI-compatible inference
marketplace. It is registered as a first-class HermesOS Cloud aggregator
(same shape as Venice / CrofAI / Bankr) so the WebUI model picker can set
``provider: surplus`` and the agent resolves a base_url + key instead of
failing with "Provider 'surplus' is set in config.yaml but no API key was
found."
"""

import pytest

from hermes_cli.auth import (
    PROVIDER_REGISTRY,
    resolve_provider,
    get_api_key_provider_status,
    resolve_api_key_provider_credentials,
)


SURPLUS_BASE_URL = "https://www.surplusintelligence.ai/api/inference/v1"


class TestSurplusProviderRegistry:
    def test_registered(self):
        assert "surplus" in PROVIDER_REGISTRY

    def test_name(self):
        assert PROVIDER_REGISTRY["surplus"].name == "Surplus Intelligence"

    def test_auth_type(self):
        assert PROVIDER_REGISTRY["surplus"].auth_type == "api_key"

    def test_inference_base_url(self):
        assert PROVIDER_REGISTRY["surplus"].inference_base_url == SURPLUS_BASE_URL

    def test_api_key_env_vars(self):
        assert PROVIDER_REGISTRY["surplus"].api_key_env_vars == ("SURPLUS_API_KEY",)

    def test_base_url_env_var(self):
        assert PROVIDER_REGISTRY["surplus"].base_url_env_var == "SURPLUS_BASE_URL"


class TestSurplusCredentials:
    def test_resolve_provider_by_slug(self, monkeypatch):
        monkeypatch.setenv("SURPLUS_API_KEY", "inf_test_12345678")
        assert resolve_provider("surplus") == "surplus"

    def test_status_configured(self, monkeypatch):
        monkeypatch.setenv("SURPLUS_API_KEY", "inf_test_12345678")
        assert get_api_key_provider_status("surplus")["configured"]

    def test_status_not_configured(self, monkeypatch):
        monkeypatch.delenv("SURPLUS_API_KEY", raising=False)
        assert not get_api_key_provider_status("surplus")["configured"]

    def test_resolve_credentials(self, monkeypatch):
        monkeypatch.setenv("SURPLUS_API_KEY", "inf_test_12345678")
        monkeypatch.delenv("SURPLUS_BASE_URL", raising=False)
        creds = resolve_api_key_provider_credentials("surplus")
        assert creds["api_key"] == "inf_test_12345678"
        assert creds["base_url"] == SURPLUS_BASE_URL

    def test_custom_base_url_override(self, monkeypatch):
        monkeypatch.setenv("SURPLUS_API_KEY", "inf_test_12345678")
        monkeypatch.setenv("SURPLUS_BASE_URL", "https://proxy.surplus.example/v1")
        creds = resolve_api_key_provider_credentials("surplus")
        assert creds["base_url"] == "https://proxy.surplus.example/v1"
