"""Hivra fork: provider-plugin behaviour for Venice / Surplus / Bankr (fork-only module).

Everything here is consumed by the bundled provider plugins under
``plugins/model-providers/{venice,surplus,bankr}`` through upstream's public ProviderProfile hooks
(``fetch_models``, ``build_api_kwargs_extras``). No upstream file carries this logic, so a
future upstream sync cannot conflict with it.

* ``SortedCatalogMixin`` -- family-sorted live catalogs for marketplace-scale providers
  (Surplus returns hundreds of models in seller-availability order, so a user hunting for
  ``claude-opus-4-8-fast`` found it 60 rows from ``claude-opus-4.6-fast``).
* ``VeniceProfile`` -- cross-vendor model-slug remap (Venice 404s ``anthropic/claude-sonnet-4``
  and the turn aborts non-retryably) and the per-profile ``venice.character_slug`` injection.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from providers.base import ProviderProfile

logger = logging.getLogger(__name__)
_REMAPS_LOGGED: set[tuple[str, str]] = set()


def sort_discovered_model_ids(ids: list[str]) -> list[str]:
    """Case-insensitive alphabetical sort so related families cluster; never raises."""
    try:
        return sorted(ids, key=lambda m: str(m).lower())
    except Exception:
        return ids


class SortedCatalogMixin:
    """Mixin for a ``ProviderProfile`` subclass: family-sort the live ``/models`` result."""

    def fetch_models(self, *args: Any, **kwargs: Any) -> Optional[list[str]]:
        live = super().fetch_models(*args, **kwargs)  # type: ignore[misc]
        return sort_discovered_model_ids(list(live)) if live else live


# ---------------------------------------------------------------------------
# Venice cross-vendor model aliasing
# ---------------------------------------------------------------------------
# Venice hosts Claude / GPT / Gemini / Kimi / Grok under its OWN model ids, which differ from the
# OpenRouter/Anthropic slugs users carry over. Values are verified-live Venice ids only; we never
# invent an unvalidated id.
VENICE_MODEL_ALIASES: dict[str, str] = {
    "anthropic/claude-sonnet-4": "claude-sonnet-4-6",
    "anthropic/claude-sonnet-4.6": "claude-sonnet-4-6",
    "anthropic/claude-sonnet-4.5": "claude-sonnet-4-5",
    "anthropic/claude-opus-4.8": "claude-opus-4-8",
    "anthropic/claude-opus-4.7": "claude-opus-4-7",
    "anthropic/claude-opus-4.6": "claude-opus-4-6",
    "anthropic/claude-opus-4.5": "claude-opus-4-5",
    "anthropic/claude-fable-5": "claude-fable-5",
    "claude-sonnet-4": "claude-sonnet-4-6",
    "claude-opus-4": "claude-opus-4-8",
    "openai/gpt-5.5": "openai-gpt-55",
    "google/gemini-3-flash-preview": "gemini-3-flash-preview",
    "moonshotai/kimi-k2.6": "kimi-k2-6",
}

# Vendor prefixes stripped by the safe heuristic; a candidate is accepted only if it is already a
# known-good Venice id (a value in the table).
_VENICE_VENDOR_PREFIXES: tuple[str, ...] = (
    "anthropic/", "openai/", "google/", "x-ai/", "moonshotai/", "deepseek/", "qwen/",
)


def normalize_venice_model_id(model: Optional[str]) -> tuple[str, Optional[str]]:
    """Map a foreign/legacy model slug onto its Venice equivalent.

    Returns ``(normalized_model, original)`` where ``original`` is the pre-remap slug only when a
    remap actually happened (else ``None``, a passthrough).
    """
    model_str = (model or "").strip()
    if not model_str:
        return (model_str, None)

    known_venice_ids = set(VENICE_MODEL_ALIASES.values())
    lowered = model_str.lower()
    if lowered in known_venice_ids:
        return (model_str, None)

    target = VENICE_MODEL_ALIASES.get(lowered)
    if target and target != model_str:
        return (target, model_str)

    for prefix in _VENICE_VENDOR_PREFIXES:
        if lowered.startswith(prefix):
            candidate = lowered[len(prefix):].replace(".", "-")
            if candidate in known_venice_ids and candidate != model_str:
                return (candidate, model_str)
            break
    return (model_str, None)


def configured_venice_character_slug() -> str:
    """``venice.character_slug`` from the active profile's config.yaml, or ``""``."""
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        section = cfg.get("venice") if isinstance(cfg, dict) else None
        slug = section.get("character_slug") if isinstance(section, dict) else None
        return slug.strip() if isinstance(slug, str) else ""
    except Exception as exc:  # never break the chat request over a nicety
        logger.debug("venice character slug lookup skipped: %s", exc)
        return ""


class VeniceProfile(SortedCatalogMixin, ProviderProfile):
    """Venice: forgiving model slugs + optional base character, on top of the stock profile."""

    def build_api_kwargs_extras(
        self, *, reasoning_config: dict | None = None, **context: Any
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        extra_body: dict[str, Any] = {}
        top_level: dict[str, Any] = {}

        mapped, original = normalize_venice_model_id(context.get("model"))
        if original is not None:
            top_level["model"] = mapped
            if (original, mapped) not in _REMAPS_LOGGED:  # log once per process, not per request
                _REMAPS_LOGGED.add((original, mapped))
                logger.info("Venice: remapped foreign model id %r -> %r (Venice equivalent)", original, mapped)

        slug = configured_venice_character_slug()
        if slug:
            extra_body["venice_parameters"] = {"character_slug": slug}
        return extra_body, top_level
