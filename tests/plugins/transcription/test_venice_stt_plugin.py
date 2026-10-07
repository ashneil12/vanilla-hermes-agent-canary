"""Venice STT ships as a bundled backend plugin (``plugins/stt/venice``) plus the
``venice-autopair`` last-resort auto-detect seam in ``tools/transcription_tools.py``
(hermes-fork). Network-free."""

from __future__ import annotations

import pytest


class _Resp:
    def __init__(self, status=200, body=None, text=""):
        self.status_code = status
        self._body = body if body is not None else {"text": " hello world "}
        self.text = text

    def json(self):
        return self._body


@pytest.fixture
def venice_stt(monkeypatch, tmp_path):
    monkeypatch.setenv("VENICE_API_KEY", "test-key")
    monkeypatch.delenv("VENICE_BASE_URL", raising=False)
    import plugins.stt.venice as mod

    monkeypatch.setattr(mod, "_load_venice_config", lambda: {})
    audio = tmp_path / "clip.ogg"
    audio.write_bytes(b"OggS-fake")
    return mod, str(audio)


def _capture_post(monkeypatch, resp):
    import requests

    seen = {}

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return resp

    monkeypatch.setattr(requests, "post", fake_post)
    return seen


def test_not_a_builtin_so_the_plugin_registers():
    from agent import transcription_registry
    from tools.transcription_tools import BUILTIN_STT_PROVIDERS

    assert "venice" not in BUILTIN_STT_PROVIDERS
    assert "venice" not in transcription_registry._BUILTIN_NAMES


def test_bundled_manifest_auto_loads_and_registers():
    from hermes_cli.plugins import _ensure_plugins_discovered
    from agent.transcription_registry import get_provider

    _ensure_plugins_discovered()
    assert get_provider("venice") is not None


def test_transcribe_success_posts_multipart(venice_stt, monkeypatch):
    mod, audio = venice_stt
    seen = _capture_post(monkeypatch, _Resp())
    out = mod.VeniceTranscriptionProvider().transcribe(audio, language="en")
    assert out == {"success": True, "transcript": "hello world", "provider": "venice"}
    assert seen["url"] == "https://api.venice.ai/api/v1/audio/transcriptions"
    assert seen["headers"]["Authorization"] == "Bearer test-key"
    assert seen["data"] == {"model": "openai/whisper-large-v3", "response_format": "json", "language": "en"}


def test_http_error_becomes_error_envelope(venice_stt, monkeypatch):
    mod, audio = venice_stt
    _capture_post(monkeypatch, _Resp(status=404, body={"error": {"message": "no such model"}}))
    out = mod.VeniceTranscriptionProvider().transcribe(audio)
    assert out["success"] is False
    assert "HTTP 404" in out["error"] and "no such model" in out["error"]


def test_missing_key_is_error_envelope_not_raise(venice_stt, monkeypatch):
    mod, audio = venice_stt
    monkeypatch.delenv("VENICE_API_KEY")
    out = mod.VeniceTranscriptionProvider().transcribe(audio)
    assert out["success"] is False and "VENICE_API_KEY" in out["error"]


class TestVeniceAutopairSeam:
    """venice-autopair: unset stt.provider on a box with no local/other cloud STT picks venice."""

    def _no_other_backend(self, monkeypatch):
        import tools.transcription_tools as tt

        monkeypatch.setattr(tt, "_detect_local_backend", lambda: None)
        monkeypatch.setattr(tt, "_CLOUD_PROVIDER_SPECS", {})
        return tt

    def test_unset_provider_with_venice_key_picks_venice(self, monkeypatch):
        tt = self._no_other_backend(monkeypatch)
        monkeypatch.setenv("VENICE_API_KEY", "k")
        assert tt._get_provider({"enabled": True}) == "venice"

    def test_no_key_is_none(self, monkeypatch):
        tt = self._no_other_backend(monkeypatch)
        monkeypatch.delenv("VENICE_API_KEY", raising=False)
        assert tt._get_provider({"enabled": True}) == "none"

    def test_other_cloud_provider_still_wins_when_available(self, monkeypatch):
        import tools.transcription_tools as tt

        monkeypatch.setattr(tt, "_detect_local_backend", lambda: None)
        monkeypatch.setattr(tt, "_CLOUD_PROVIDER_SPECS",
                            {"groq": (lambda: True, lambda: True, "w", "using groq")})
        monkeypatch.setenv("VENICE_API_KEY", "k")
        assert tt._get_provider({"enabled": True}) == "groq"

    def test_explicit_provider_is_never_overridden(self, monkeypatch):
        tt = self._no_other_backend(monkeypatch)
        monkeypatch.setenv("VENICE_API_KEY", "k")
        assert tt._get_provider({"enabled": True, "provider": "openai"}) != "venice"
