"""Video image-to-video input handling.

"Turn this image into a video" passes a LOCAL image (often one the agent just
generated). Venice video accepts a data URL but not a local path, so the tool
must auto-encode local paths / base64 into a data: URL (downscaled for the
managed-proxy cap). HTTP(S) and existing data: URLs pass through untouched.
"""

import base64

import pytest

import tools.video_generation_tool as vg

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


def test_http_url_passthrough():
    assert vg._coerce_image_to_data_url("https://x/i.png") == "https://x/i.png"
    assert vg._coerce_image_to_data_url("HTTP://x/i.png") == "HTTP://x/i.png"


def test_data_url_passthrough():
    d = "data:image/png;base64,AAAA"
    assert vg._coerce_image_to_data_url(d) == d


def test_empty_passthrough():
    assert vg._coerce_image_to_data_url("") == ""


def test_local_path_becomes_data_url(tmp_path):
    p = tmp_path / "frame.png"
    Image.new("RGB", (320, 200), (10, 120, 200)).save(p, format="PNG")
    out = vg._coerce_image_to_data_url(str(p))
    assert out.startswith("data:image/"), out
    assert ";base64," in out
    # round-trips to real image bytes
    b64 = out.split(",", 1)[1]
    raw = base64.b64decode(b64)
    assert raw[:8] == b"\x89PNG\r\n\x1a\n" or raw[:3] == b"\xff\xd8\xff"


def test_large_local_image_downscaled_under_budget(tmp_path):
    import os

    p = tmp_path / "big.png"
    # random noise → poor compression → comfortably over a 3 MB budget
    Image.frombytes("RGB", (2600, 2600), os.urandom(2600 * 2600 * 3)).save(p, format="PNG")
    out = vg._coerce_image_to_data_url(str(p), budget=3_000_000)
    assert out.startswith("data:image/")
    raw = base64.b64decode(out.split(",", 1)[1])
    assert len(raw) <= 3_000_000


def test_handler_encodes_local_image_url(monkeypatch, tmp_path):
    p = tmp_path / "src.png"
    Image.new("RGB", (320, 200), (200, 50, 50)).save(p, format="PNG")

    captured = {}

    class _Provider:
        def default_model(self):
            return "veo-3.1"

        def generate(self, prompt, **kwargs):
            captured.update(kwargs)
            return '{"success": true, "video": "/v.mp4"}'

    monkeypatch.setattr(vg, "_resolve_active_provider", lambda: _Provider())
    monkeypatch.setattr(vg, "_read_configured_video_provider", lambda: "venice")
    monkeypatch.setattr(vg, "_read_configured_video_model", lambda: None)

    vg._handle_video_generate({"prompt": "animate it", "image_url": str(p)})
    assert captured["image_url"].startswith("data:image/"), captured.get("image_url")
