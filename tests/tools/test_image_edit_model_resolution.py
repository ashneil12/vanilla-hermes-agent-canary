"""Edit-model resolution + reference-conditioned generation.

Venice's /image/edit default (firered-image-edit) is a weak editor that drifts
from the source. These tests lock in that edits instead use a strong model
matched to the user's generation model, that "auto" aspect ratio is omitted
(preserve the source frame; some models 400 on literal "auto"), and that
image_generate with reference_images routes to the edit path.
"""

import os
import json

import pytest

import tools.image_edit_tool as ie


class TestResolveEditModel:
    def teardown_method(self):
        os.environ.pop("VENICE_IMAGE_MODEL", None)

    def test_explicit_override_wins(self):
        assert ie._resolve_edit_model("nano-banana-pro-edit") == "nano-banana-pro-edit"

    def test_never_defaults_to_weak_firered(self):
        os.environ.pop("VENICE_IMAGE_MODEL", None)
        assert ie._resolve_edit_model(None) == ie.STRONG_DEFAULT_EDIT_MODEL
        assert ie._resolve_edit_model(None) != "firered-image-edit"

    def test_gen_model_maps_to_edit_variant(self):
        os.environ["VENICE_IMAGE_MODEL"] = "nano-banana-2"
        assert ie._resolve_edit_model(None) == "nano-banana-2-edit"

    def test_seedream_gen_maps_to_edit(self):
        os.environ["VENICE_IMAGE_MODEL"] = "seedream-v4"
        assert ie._resolve_edit_model(None) == "seedream-v4-edit"

    def test_special_case_mapping(self):
        os.environ["VENICE_IMAGE_MODEL"] = "grok-imagine-image"
        assert ie._resolve_edit_model(None) == "grok-imagine-edit"

    def test_gen_model_without_edit_variant_falls_back(self):
        os.environ["VENICE_IMAGE_MODEL"] = "venice-sd35"  # no edit variant
        assert ie._resolve_edit_model(None) == ie.STRONG_DEFAULT_EDIT_MODEL

    def test_already_edit_model_passthrough(self):
        os.environ["VENICE_IMAGE_MODEL"] = "qwen-image-2-edit"
        assert ie._resolve_edit_model(None) == "qwen-image-2-edit"


class TestEditAspectRatio:
    """image_edit must omit aspect_ratio when 'auto' and send a concrete one otherwise."""

    def _patch(self, monkeypatch, captured):
        monkeypatch.setattr(ie, "_resolve_credentials", lambda: ("k", "https://api.venice.ai/api/v1"))
        monkeypatch.setattr(ie, "_open_image_for_upload", lambda image: (b"\x89PNG\r\n\x1a\n", "x.png"))

        class _Resp:
            status_code = 200
            headers = {"content-type": "image/png"}
            content = b"out"

        def fake_post(endpoint, *, image_bytes, image_name, data_fields, api_key, base_url, timeout=180):
            captured["data"] = dict(data_fields)
            return _Resp()

        monkeypatch.setattr(ie, "_post_multipart", fake_post)
        monkeypatch.setattr(ie, "_save_response_image", lambda response, prefix: ie.Path("/tmp/out.png"))

    def test_auto_is_omitted(self, monkeypatch):
        captured = {}
        self._patch(monkeypatch, captured)
        res = ie.image_edit_tool(image="x", prompt="move subject right", aspect_ratio="auto")
        assert '"success": true' in res
        assert "aspect_ratio" not in captured["data"], "auto must not be sent"

    def test_concrete_ratio_is_sent(self, monkeypatch):
        captured = {}
        self._patch(monkeypatch, captured)
        ie.image_edit_tool(image="x", prompt="widen", aspect_ratio="16:9")
        assert captured["data"].get("aspect_ratio") == "16:9"

    def test_default_model_is_strong_not_firered(self, monkeypatch):
        captured = {}
        os.environ.pop("VENICE_IMAGE_MODEL", None)
        self._patch(monkeypatch, captured)
        ie.image_edit_tool(image="x", prompt="p")
        assert captured["data"]["model"] == ie.STRONG_DEFAULT_EDIT_MODEL
        assert captured["data"]["model"] != "firered-image-edit"


class TestGenerateWithReference:
    """image_generate with reference_images routes to the edit path."""

    def test_single_reference_calls_image_edit(self, monkeypatch):
        import tools.image_generation_tool as ig

        calls = {}

        def fake_edit(image, prompt, aspect_ratio="auto", **kw):
            calls["edit"] = {"image": image, "prompt": prompt, "aspect_ratio": aspect_ratio}
            return '{"success": true, "image": "/e.png"}'

        monkeypatch.setattr(ie, "image_edit_tool", fake_edit)
        out = ig._handle_image_generate(
            {"prompt": "make it night", "reference_images": ["/prior.png"], "aspect_ratio": "landscape"}
        )
        assert calls.get("edit") == {
            "image": "/prior.png",
            "prompt": "make it night",
            "aspect_ratio": "16:9",
        }
        assert "success" in out

    def test_multiple_references_call_compose(self, monkeypatch):
        import tools.image_generation_tool as ig

        calls = {}

        def fake_compose(images, prompt, aspect_ratio="auto", **kw):
            calls["compose"] = {"images": images, "prompt": prompt, "aspect_ratio": aspect_ratio}
            return '{"success": true, "image": "/c.png"}'

        monkeypatch.setattr(ie, "image_compose_tool", fake_compose)
        ig._handle_image_generate(
            {"prompt": "merge", "reference_images": ["/a.png", "/b.png"], "aspect_ratio": "portrait"}
        )
        assert calls["compose"]["images"] == ["/a.png", "/b.png"]
        assert calls["compose"]["aspect_ratio"] == "9:16"

    def test_no_reference_does_not_route_to_edit(self, monkeypatch):
        import tools.image_generation_tool as ig

        # No reference → must NOT call edit; falls through to normal dispatch.
        def boom(*a, **k):
            raise AssertionError("should not edit without a reference")

        monkeypatch.setattr(ie, "image_edit_tool", boom)
        monkeypatch.setattr(ig, "_dispatch_to_plugin_provider", lambda prompt, ar: '{"success": true, "image": "/g.png"}')
        out = ig._handle_image_generate({"prompt": "a cat"})
        assert "success" in out


class TestImageEditRegistryDispatch:
    """Image edit tools must accept the registry's handler(args, **kwargs) call shape."""

    @pytest.mark.parametrize(
        ("tool_name", "function_name", "args", "expected"),
        [
            ("image_edit", "image_edit_tool", {"image": "in.png", "prompt": "move right"}, "edit"),
            ("image_compose", "image_compose_tool", {"images": ["a.png", "b.png"], "prompt": "merge"}, "compose"),
            ("image_upscale", "image_upscale_tool", {"image": "in.png"}, "upscale"),
            ("image_remove_background", "image_remove_background_tool", {"image": "in.png"}, "remove"),
        ],
    )
    def test_registry_dispatch_passes_args_dict(self, monkeypatch, tool_name, function_name, args, expected):
        from tools.registry import registry

        def fake_tool(**kwargs):
            return json.dumps({"success": True, "called": expected, "kwargs": kwargs})

        monkeypatch.setattr(ie, function_name, fake_tool)
        out = json.loads(registry.dispatch(tool_name, args))
        assert out["success"] is True
        assert out["called"] == expected
