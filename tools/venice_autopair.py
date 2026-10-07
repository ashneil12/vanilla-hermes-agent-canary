"""Venice auto-pair for media backends (fork-only module).

HermesOS managed boxes carry ONE ``VENICE_API_KEY`` that covers chat + image +
video + speech. A Venice-only user must get multimodal tools without touching
``config.yaml`` (see dashboard/docs/venice-multimodal-runbook.md, "Auto-pair").

Upstream deliberately keeps unset ``image_gen.provider`` / ``video_gen.provider``
on the legacy FAL path ("a cloud key alone must not opt a user into a paid
backend"). On managed Venice boxes the Venice key IS the platform multimodal key,
so the fork flips only the *unset* default; an explicit config value always wins.

Upstream call sites (one seam, name ``venice-autopair``, marker
``# hermes-fork: venice-autopair``):

- ``tools/image_generation_tool.py::_read_configured_image_provider``
- ``agent/provider_registry.py::configured_provider_name`` (image_gen/video_gen registries)
- ``tools/transcription_tools.py::_get_provider`` (auto-detect tail)

TTS is deliberately NOT auto-paired: ``DEFAULT_CONFIG["tts"]["provider"]`` is seeded
to ``edge`` so "unset" never occurs; Venice TTS is selected by an explicit
``tts.provider: venice`` (what the Media settings write).
"""

from __future__ import annotations

import os
from typing import Optional

# Config sections whose unset provider defaults to Venice when the key is present.
AUTOPAIR_SECTIONS = frozenset({"image_gen", "video_gen", "stt"})


def default_provider(section: str) -> Optional[str]:
    """``"venice"`` when *section* is auto-paired and ``VENICE_API_KEY`` is set, else ``None``."""
    if section not in AUTOPAIR_SECTIONS:
        return None
    return "venice" if os.environ.get("VENICE_API_KEY", "").strip() else None
