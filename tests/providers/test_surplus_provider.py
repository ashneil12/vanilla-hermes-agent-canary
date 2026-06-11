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

import hermes_cli.model_switch as ms
from hermes_cli.model_switch import (
    provider_has_resolvable_credentials,
    switch_model,
)

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


# ---------------------------------------------------------------------------
# Model-switch credential guard (folded in from the former
# tests/hermes_cli/test_model_switch_credential_guard.py). It lives in this
# existing, already-on-main file rather than as a net-new module on purpose:
# the sharded CI runner resets its per-file checkout to origin/main mid-run
# (a shard-mate test), which deletes any PR-added file before its turn to run.
# The guard behaviour is surplus-centric (surplus is the configured BYOK
# provider in every case below), so it belongs here naturally.
#
# Behaviour under test: the picker can offer models from providers the box has
# no key for. Switching to one used to persist the dead provider into
# config.yaml and "succeed", after which every session aborted at agent init
# ("Provider 'X' is set in config.yaml but no API key was found"). switch_model
# now refuses to persist a provider whose credentials can't be resolved.
# See hermes_cli.model_switch.provider_has_resolvable_credentials.
# ---------------------------------------------------------------------------


SURPLUS_BASE_URL = "https://www.surplusintelligence.ai/api/inference/v1"


class TestProviderHasResolvableCredentials:
    def test_configured_api_key_provider(self, monkeypatch):
        monkeypatch.setenv("SURPLUS_API_KEY", "inf_test_12345678")
        assert provider_has_resolvable_credentials("surplus")

    def test_unconfigured_api_key_provider_rejected(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        # Only surplus is configured — openai-api must not resolve.
        monkeypatch.setattr(ms, "get_authenticated_provider_slugs", lambda **kw: ["surplus"])
        assert not provider_has_resolvable_credentials("openai-api")

    def test_already_resolved_key_passes(self):
        # A real key/token already resolved by the caller short-circuits True,
        # regardless of env (covers OAuth tokens resolved into api_key).
        assert provider_has_resolvable_credentials("openai-api", api_key="sk-abc12345")

    def test_no_auth_local_providers_pass(self):
        assert provider_has_resolvable_credentials("lmstudio")
        assert provider_has_resolvable_credentials("custom")
        assert provider_has_resolvable_credentials("custom:mine")
        assert provider_has_resolvable_credentials(
            "anything", base_url="http://127.0.0.1:1234/v1"
        )
        assert provider_has_resolvable_credentials(
            "anything", base_url="http://localhost:8000/v1"
        )

    def test_no_concrete_provider_passes(self):
        # "auto" / empty resolve at runtime — nothing to validate.
        assert provider_has_resolvable_credentials("auto")
        assert provider_has_resolvable_credentials("")

    def test_user_declared_provider_passes(self):
        # A providers: block in config.yaml carries its own key reference.
        assert provider_has_resolvable_credentials(
            "myrouter",
            user_providers={"myrouter": {"base_url": "https://x/v1", "key_env": "MY_KEY"}},
        )

    def test_no_auth_placeholder_passes(self):
        assert provider_has_resolvable_credentials("custom", api_key="no-key-required")

    def test_unavailable_listing_does_not_block(self, monkeypatch):
        # If the authoritative listing can't be built (offline, etc.) we must
        # NOT block — a false rejection is worse than a permissive pass that the
        # runtime catches. Empty listing → allow.
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.setattr(ms, "get_authenticated_provider_slugs", lambda **kw: [])
        assert provider_has_resolvable_credentials("deepseek")

    def test_oauth_provider_authed_via_listing_passes(self, monkeypatch):
        # anthropic is an api_key provider in the registry but can also be
        # authenticated via OAuth. A missing ANTHROPIC_API_KEY must fall through
        # to the authed listing (which captures OAuth) rather than hard-reject.
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr(
            ms, "get_authenticated_provider_slugs", lambda **kw: ["anthropic"]
        )
        assert provider_has_resolvable_credentials("anthropic")


class TestSwitchModelCredentialGuard:
    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        monkeypatch.setenv("SURPLUS_API_KEY", "inf_test_12345678")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        # Deterministic authed set: only surplus is configured on this box.
        monkeypatch.setattr(ms, "get_authenticated_provider_slugs", lambda **kw: ["surplus"])

    def _switch(self, **overrides):
        kwargs = dict(
            raw_input="gpt-5.5-pro",
            current_provider="surplus",
            current_model="claude-haiku-4.5",
            current_base_url=SURPLUS_BASE_URL,
            current_api_key="inf_test_12345678",
            is_global=True,
        )
        kwargs.update(overrides)
        return switch_model(**kwargs)

    def test_explicit_keyless_provider_rejected(self):
        """`/model gpt-5.5-pro --provider openai-api` with no OPENAI_API_KEY."""
        res = self._switch(explicit_provider="openai-api")
        assert not res.success
        assert res.target_provider == "openai-api"
        assert "OPENAI_API_KEY" in res.error_message

    def test_bare_model_routing_to_keyless_provider_rejected(self, monkeypatch):
        """A bare model name that detection routes to a keyless provider."""
        monkeypatch.setattr(ms, "resolve_alias", lambda raw, prov: None)
        monkeypatch.setattr(
            "hermes_cli.models.detect_provider_for_model",
            lambda model, current: ("openai-api", model),
        )
        res = self._switch(explicit_provider="", is_global=False)
        assert not res.success
        assert res.target_provider == "openai-api"

    def test_configured_provider_allowed(self, monkeypatch):
        """With the key present the switch proceeds normally."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-1234567890")
        monkeypatch.setattr(
            "hermes_cli.models.validate_requested_model",
            lambda *a, **kw: {
                "accepted": True,
                "persist": True,
                "recognized": True,
                "message": None,
            },
        )
        res = self._switch(explicit_provider="openai-api")
        assert res.success, f"unexpected rejection: {res.error_message}"
        assert res.target_provider == "openai-api"

    def test_same_provider_repick_not_blocked(self, monkeypatch):
        """Re-picking a model on the current (working) provider is never gated
        on a credential re-check — even if the authed listing momentarily can't
        see it."""
        monkeypatch.setattr(ms, "get_authenticated_provider_slugs", lambda **kw: [])
        monkeypatch.setattr(ms, "resolve_alias", lambda raw, prov: None)
        monkeypatch.setattr(
            "hermes_cli.models.detect_provider_for_model", lambda model, current: None
        )
        monkeypatch.setattr(
            "hermes_cli.models.validate_requested_model",
            lambda *a, **kw: {
                "accepted": True,
                "persist": True,
                "recognized": True,
                "message": None,
            },
        )
        res = self._switch(raw_input="some-other-surplus-model", explicit_provider="")
        # provider unchanged (surplus) and no explicit provider → guard skipped.
        assert res.success, f"unexpected rejection: {res.error_message}"
        assert res.target_provider == "surplus"
