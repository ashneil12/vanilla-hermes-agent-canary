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


class TestSurplusModelOrdering:
    """The marketplace ``/v1/models`` endpoint lists models in arbitrary
    seller-availability order, so the picker must sort the live catalog or
    related variants scatter and read as "missing" (the reported bug:
    ``claude-opus-4-8-fast`` 60 rows from ``claude-opus-4.6-fast``).
    """

    def _stub_live_catalog(self, monkeypatch, catalog):
        monkeypatch.setattr(
            "hermes_cli.auth.resolve_api_key_provider_credentials",
            lambda provider_id: {
                "provider": provider_id,
                "api_key": "inf_live_key",
                "base_url": (
                    "https://www.surplusintelligence.ai/api/inference/v1"
                ),
                "source": "SURPLUS_API_KEY",
            },
        )
        monkeypatch.setattr(
            "providers.base.ProviderProfile.fetch_models",
            lambda self, *, api_key=None, timeout=8.0: list(catalog),
        )

    def test_live_models_sorted_and_variants_adjacent(self, monkeypatch):
        from hermes_cli.models import provider_model_ids

        # Arbitrary marketplace order — the two opus variants are far apart.
        unsorted = [
            "llama-3.3-70b",
            "claude-opus-4.6-fast",
            "gpt-5.4",
            "claude-opus-4-8-fast",
            "claude-opus-4.6",
        ]
        self._stub_live_catalog(monkeypatch, unsorted)

        result = provider_model_ids("surplus")

        # Sorted case-insensitively (alphabetical family grouping).
        assert result == sorted(unsorted, key=str.lower)
        # The variants the user couldn't find are now neighbours.
        assert (
            abs(
                result.index("claude-opus-4-8-fast")
                - result.index("claude-opus-4.6-fast")
            )
            <= 2
        )

    def test_fallback_models_order_preserved(self, monkeypatch):
        # When the live fetch yields nothing, the small hand-ordered
        # ``fallback_models`` curated list is returned verbatim (NOT sorted).
        from hermes_cli.models import provider_model_ids

        monkeypatch.setattr(
            "hermes_cli.auth.resolve_api_key_provider_credentials",
            lambda provider_id: {
                "provider": provider_id,
                "api_key": "inf_live_key",
                "base_url": (
                    "https://www.surplusintelligence.ai/api/inference/v1"
                ),
                "source": "SURPLUS_API_KEY",
            },
        )
        monkeypatch.setattr(
            "providers.base.ProviderProfile.fetch_models",
            lambda self, *, api_key=None, timeout=8.0: None,
        )

        assert provider_model_ids("surplus") == ["claude-opus-4.6", "llama-3.3-70b"]
