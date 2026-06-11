"""Focused tests for the Surplus Intelligence provider plugin wiring.

Surplus is added as a single ``plugins/model-providers/surplus/`` plugin;
``config.py`` and ``auth.py`` auto-wire the env editor + credential registry
from the profile, so these tests assert that auto-wiring rather than any
hand-maintained per-file entries.
"""

from __future__ import annotations

import sys
import types

import pytest

# hermes_cli.config imports python-dotenv at module load; stub it so the test
# runs without the optional dependency (mirrors test_gmi_provider.py).
if "dotenv" not in sys.modules:
    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *args, **kwargs: None
    sys.modules["dotenv"] = fake_dotenv


@pytest.fixture(autouse=True)
def _clear_provider_env(monkeypatch):
    for key in ("SURPLUS_API_KEY", "SURPLUS_BASE_URL"):
        monkeypatch.delenv(key, raising=False)


class TestSurplusProfile:
    def test_profile_registered(self):
        from providers import get_provider_profile

        p = get_provider_profile("surplus")
        assert p is not None
        assert p.base_url == "https://www.surplusintelligence.ai/api/inference/v1"
        assert p.auth_type == "api_key"
        assert "SURPLUS_API_KEY" in p.env_vars
        assert p.display_name == "Surplus Intelligence"

    @pytest.mark.parametrize(
        "alias", ["surplus", "surplus-intelligence", "surplusintelligence"]
    )
    def test_aliases_resolve(self, alias):
        from providers import get_provider_profile

        p = get_provider_profile(alias)
        assert p is not None and p.name == "surplus"


class TestSurplusConfigRegistry:
    def test_optional_env_vars_auto_injected(self):
        from hermes_cli.config import OPTIONAL_ENV_VARS

        assert "SURPLUS_API_KEY" in OPTIONAL_ENV_VARS
        assert OPTIONAL_ENV_VARS["SURPLUS_API_KEY"]["category"] == "provider"
        assert OPTIONAL_ENV_VARS["SURPLUS_API_KEY"]["password"] is True

        assert "SURPLUS_BASE_URL" in OPTIONAL_ENV_VARS
        assert OPTIONAL_ENV_VARS["SURPLUS_BASE_URL"]["category"] == "provider"
        assert OPTIONAL_ENV_VARS["SURPLUS_BASE_URL"]["password"] is False


class TestSurplusAuthRegistry:
    def test_registry_auto_extended(self):
        from hermes_cli.auth import PROVIDER_REGISTRY

        assert "surplus" in PROVIDER_REGISTRY
        cfg = PROVIDER_REGISTRY["surplus"]
        assert cfg.auth_type == "api_key"
        assert cfg.inference_base_url == (
            "https://www.surplusintelligence.ai/api/inference/v1"
        )
        assert "SURPLUS_API_KEY" in cfg.api_key_env_vars
        assert cfg.base_url_env_var == "SURPLUS_BASE_URL"

    def test_resolve_credentials_from_env(self, monkeypatch):
        from hermes_cli.auth import resolve_api_key_provider_credentials

        monkeypatch.setenv("SURPLUS_API_KEY", "inf_test_key")
        creds = resolve_api_key_provider_credentials("surplus")
        assert creds["api_key"] == "inf_test_key"
        assert creds["base_url"] == (
            "https://www.surplusintelligence.ai/api/inference/v1"
        )

    def test_base_url_override_env(self, monkeypatch):
        from hermes_cli.auth import resolve_api_key_provider_credentials

        monkeypatch.setenv("SURPLUS_API_KEY", "inf_test_key")
        monkeypatch.setenv("SURPLUS_BASE_URL", "https://proxy.example.com/v1")
        creds = resolve_api_key_provider_credentials("surplus")
        assert creds["base_url"] == "https://proxy.example.com/v1"
