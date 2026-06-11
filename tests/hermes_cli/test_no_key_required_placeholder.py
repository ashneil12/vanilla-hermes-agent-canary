"""Regression: the `no-key-required` sentinel must not be treated as a usable secret.

The resolver assigns `no-key-required` to keyless/local endpoints so the OpenAI SDK
accepts a non-empty api_key. If `has_usable_secret` accepts it, the sentinel can land
in an explicit/candidate slot (e.g. propagated to `self._explicit_api_key` via a model
switch) and PREEMPT a real env-derived key (e.g. VENICE_API_KEY) — making resumed
sessions send `Bearer no-key-required` and 401 while fresh chats work.
"""
from hermes_cli.auth import has_usable_secret


def test_no_key_sentinels_are_not_usable_secrets():
    assert has_usable_secret("no-key-required") is False
    assert has_usable_secret("no-key") is False
    assert has_usable_secret("NO-KEY-REQUIRED") is False  # case-insensitive


def test_real_secret_still_usable():
    assert has_usable_secret("VENICE_INFERENCE_KEY_GvQaE5O2laUM9KfulyxiYE") is True
    assert has_usable_secret("sk-or-v1-0123456789abcdef") is True


def test_custom_base_url_resolves_openai_api_key(monkeypatch):
    """HermesOS stores a custom provider's per-instance key in OPENAI_API_KEY paired
    with its base_url. Resolution must use it for a configured custom (non-openai.com)
    endpoint instead of falling through to 'no-key-required' — which 401s on resume.
    Covers venice/groq/gemini/nous/xai/bankr/crof/opengateway (all provider=custom).
    """
    from hermes_cli.runtime_provider import resolve_runtime_provider
    monkeypatch.setenv("OPENAI_API_KEY", "sk-hermesos-customkey-1234567890")
    for v in ("GROQ_API_KEY", "VENICE_API_KEY", "OPENROUTER_API_KEY", "NVIDIA_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    for base in ("https://api.groq.com/openai/v1", "https://api.venice.ai/api/v1",
                 "https://api.x.ai/v1", "https://inference-api.nousresearch.com/v1"):
        r = resolve_runtime_provider(requested="custom", explicit_base_url=base)
        assert r["api_key"] == "sk-hermesos-customkey-1234567890", f"{base} -> {r['api_key']!r}"


def test_reresolve_recovers_real_key_for_public_host(monkeypatch):
    """A transiently-unusable key (e.g. `no-key-required` from an empty-.env window
    during a dashboard env rewrite) must be re-resolved to the real OPENAI_API_KEY
    before it reaches a PUBLIC, key-requiring endpoint — incl. the managed-Venice proxy.
    """
    from hermes_cli.runtime_provider import reresolve_key_if_unusable_for_public_host
    monkeypatch.setenv("OPENAI_API_KEY", "sk-hermesos-customkey-1234567890")
    for v in ("VENICE_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    reloaded = {"n": 0}
    def _reloader():
        reloaded["n"] += 1
    for base in ("https://api.venice.ai/api/v1",
                 "https://hermesos.cloud/api/managed-venice/v1"):
        out = reresolve_key_if_unusable_for_public_host(
            "no-key-required", base, requested_provider="custom", env_reloader=_reloader,
        )
        assert out == "sk-hermesos-customkey-1234567890", f"{base} -> {out!r}"
    assert reloaded["n"] == 2  # env reloaded once per unusable+public re-resolution


def test_reresolve_passthrough_when_key_usable():
    """A usable key returns untouched — no env reload, no re-resolution."""
    from hermes_cli.runtime_provider import reresolve_key_if_unusable_for_public_host
    reloaded = {"n": 0}
    out = reresolve_key_if_unusable_for_public_host(
        "sk-or-v1-realusablekey0123456789",
        "https://api.venice.ai/api/v1",
        requested_provider="custom",
        env_reloader=lambda: reloaded.__setitem__("n", reloaded["n"] + 1),
    )
    assert out == "sk-or-v1-realusablekey0123456789"
    assert reloaded["n"] == 0


def test_reresolve_preserves_no_key_required_for_local_host(monkeypatch):
    """Local/keyless endpoints legitimately use the `no-key-required` placeholder —
    never reload/re-resolve for them (#28660: don't leak OPENAI_API_KEY to LAN)."""
    from hermes_cli.runtime_provider import reresolve_key_if_unusable_for_public_host
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak-to-local")
    reloaded = {"n": 0}
    for base in ("http://localhost:11434/v1", "http://127.0.0.1:1234/v1"):
        out = reresolve_key_if_unusable_for_public_host(
            "no-key-required", base, requested_provider="custom",
            env_reloader=lambda: reloaded.__setitem__("n", reloaded["n"] + 1),
        )
        assert out == "no-key-required", f"{base} -> {out!r}"
    assert reloaded["n"] == 0


def test_reresolve_returns_original_when_env_still_empty(monkeypatch):
    """Genuinely unconfigured (no key anywhere) → return the original value; never
    crash or fabricate a key. A clear downstream auth error is correct here."""
    from hermes_cli.runtime_provider import reresolve_key_if_unusable_for_public_host
    for v in ("OPENAI_API_KEY", "VENICE_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    out = reresolve_key_if_unusable_for_public_host(
        "no-key-required", "https://api.venice.ai/api/v1", requested_provider="custom",
    )
    assert out == "no-key-required"


def test_reresolve_passthrough_callable_token_provider():
    """Callable api_keys (Azure Foundry Entra ID bearer providers) are invoked by the
    SDK per request and must never be treated as a missing key."""
    from hermes_cli.runtime_provider import reresolve_key_if_unusable_for_public_host
    def token_provider():
        return "ey.token"
    out = reresolve_key_if_unusable_for_public_host(
        token_provider, "https://api.venice.ai/api/v1", requested_provider="custom",
    )
    assert out is token_provider
