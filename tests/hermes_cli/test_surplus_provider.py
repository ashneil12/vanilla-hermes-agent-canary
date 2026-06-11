"""Tests for Surplus Intelligence provider support.

Surplus Intelligence is a price-competitive, OpenAI-compatible inference
marketplace. It is registered as a first-class HermesOS Cloud aggregator
(same shape as Venice / CrofAI / Bankr) so the WebUI model picker can set
``provider: surplus`` and the agent resolves a base_url + key instead of
failing with "Provider 'surplus' is set in config.yaml but no API key was
found."
"""

import pytest

import hermes_cli.model_switch as ms
from hermes_cli.auth import (
    PROVIDER_REGISTRY,
    resolve_provider,
    get_api_key_provider_status,
    resolve_api_key_provider_credentials,
)
from hermes_cli.model_switch import (
    provider_has_resolvable_credentials,
    switch_model,
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


# ---------------------------------------------------------------------------
# Model-switch credential guard
#
# The desktop / webchat model picker can offer models from the full catalog,
# including providers the box has no key for. Switching to one used to write the
# new provider into config.yaml and "succeed", after which every subsequent
# session aborted at agent init with::
#
#     Provider 'openai-api' is set in config.yaml but no API key was found.
#
# …bricking chat until config.yaml was fixed out-of-band. ``switch_model`` now
# refuses to persist a provider whose credentials can't be resolved, leaving the
# working config intact. The surplus scenario above (surplus configured,
# openai-api not) is the exact brick case, so these live alongside it.
#
# (Co-located here rather than in a standalone test_model_switch_credential_guard
# module: a brand-new top-level test file intermittently fails the per-file CI
# sharder with exit-4 "file not found" — see scripts/run_tests_parallel.py — so
# the guard tests ride along in this already-tracked module.)
# ---------------------------------------------------------------------------


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
