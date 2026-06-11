"""Hermes-native port tests for the Lossless Context Management engine."""

from __future__ import annotations

import json
from unittest.mock import patch


def _messages():
    return [
        {"role": "system", "content": "You are Hermes."},
        {"role": "user", "content": "Kickoff: build the billing page."},
        {"role": "assistant", "content": "Acknowledged."},
        {"role": "user", "content": "Important retained fact: Apollo secret is blue-copper."},
        {"role": "assistant", "content": "I will remember Apollo secret is blue-copper."},
        {"role": "user", "content": "Now continue with the implementation."},
        {"role": "assistant", "content": "Continuing."},
    ]


def test_lossless_context_engine_loads_from_repo_plugin_slot():
    from plugins.context_engine import discover_context_engines, load_context_engine

    names = {name for name, _description, available in discover_context_engines() if available}
    assert "lossless" in names

    engine = load_context_engine("lossless")
    assert engine is not None
    assert engine.name == "lossless"
    assert {schema["name"] for schema in engine.get_tool_schemas()} >= {
        "lcm_grep",
        "lcm_describe",
        "lcm_expand",
        "lcm_status",
    }


def test_lossless_compress_stores_raw_messages_and_keeps_retrieval_lossless(tmp_path):
    from plugins.context_engine.lossless import LosslessContextEngine

    engine = LosslessContextEngine()
    engine.update_model(model="test-model", context_length=120_000)
    engine.on_session_start("sess-1", hermes_home=str(tmp_path), conversation_id="chat-1")

    compressed = engine.compress(_messages(), current_tokens=90_000)

    # Compression should shorten active prompt context but keep a recovery marker.
    assert len(compressed) < len(_messages())
    summary_text = "\n".join(str(msg.get("content", "")) for msg in compressed)
    assert "LOSSLESS CONTEXT" in summary_text
    assert "lcm_grep" in summary_text

    grep = json.loads(engine.handle_tool_call("lcm_grep", {"pattern": "Apollo secret", "mode": "full_text"}))
    assert grep["success"] is True
    assert grep["total_matches"] >= 1
    assert "blue-copper" in grep["content"]

    message_id = grep["matches"][0]["id"]
    described = json.loads(engine.handle_tool_call("lcm_describe", {"id": message_id}))
    assert described["success"] is True
    assert described["item"]["content"] == "Important retained fact: Apollo secret is blue-copper."


def test_lossless_expand_can_recover_summary_sources(tmp_path):
    from plugins.context_engine.lossless import LosslessContextEngine

    engine = LosslessContextEngine()
    engine.update_model(model="test-model", context_length=120_000)
    engine.on_session_start("sess-2", hermes_home=str(tmp_path), conversation_id="chat-2")
    engine.compress(_messages(), current_tokens=90_000)

    grep = json.loads(engine.handle_tool_call("lcm_grep", {"pattern": "LOSSLESS CONTEXT", "scope": "summaries"}))
    assert grep["success"] is True
    assert grep["matches"]
    summary_id = grep["matches"][0]["id"]

    expanded = json.loads(
        engine.handle_tool_call(
            "lcm_expand",
            {"summaryIds": [summary_id], "includeMessages": True, "tokenCap": 4_000},
        )
    )
    assert expanded["success"] is True
    assert "Apollo secret is blue-copper" in expanded["content"]
    assert summary_id in expanded["expanded_summary_ids"]


def test_lossless_live_tool_call_indexes_current_messages(tmp_path):
    from plugins.context_engine.lossless import LosslessContextEngine

    engine = LosslessContextEngine()
    engine.on_session_start("sess-live", hermes_home=str(tmp_path), conversation_id="chat-live")

    result = json.loads(
        engine.handle_tool_call(
            "lcm_grep",
            {"pattern": "live-only breadcrumb", "mode": "full_text"},
            messages=[{"role": "user", "content": "A live-only breadcrumb before compression."}],
        )
    )

    assert result["success"] is True
    assert result["total_matches"] == 1
    assert "live-only breadcrumb" in result["content"]


def test_lossless_engine_can_be_selected_by_context_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    cfg = {"context": {"engine": "lossless"}, "agent": {}}

    with (
        patch("hermes_cli.config.load_config", return_value=cfg),
        patch("agent.model_metadata.get_model_context_length", return_value=131_072),
        patch("run_agent.get_tool_definitions", return_value=[]),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("run_agent.OpenAI"),
    ):
        from run_agent import AIAgent

        agent = AIAgent(
            model="test-model",
            api_key="test-key-1234567890",
            base_url="https://openrouter.ai/api/v1",
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
        )

    engine = getattr(agent, "context_compressor")
    valid_tool_names = getattr(agent, "valid_tool_names")
    assert engine.name == "lossless"
    assert engine.context_length == 131_072
    assert "lcm_grep" in valid_tool_names
    assert "lcm_status" in valid_tool_names


def test_lossless_preflight_respects_token_threshold(tmp_path):
    from plugins.context_engine.lossless import LosslessContextEngine

    engine = LosslessContextEngine()
    engine.update_model(model="test-model", context_length=1_000)
    engine.on_session_start("sess-preflight", hermes_home=str(tmp_path))

    assert engine.has_content_to_compress(_messages()) is True
    assert engine.should_compress_preflight(_messages()) is False

    large_messages = _messages() + [
        {"role": "user", "content": "x" * 4_000},
        {"role": "assistant", "content": "ok"},
    ]
    assert engine.should_compress_preflight(large_messages) is True
