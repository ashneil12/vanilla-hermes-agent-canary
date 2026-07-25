"""OpenGateway provider profile.

OpenGateway (https://opengateway.gitlawb.com) is gitlawb's open,
OpenAI-compatible LLM gateway. Any token works while the partnership window is
open. From Hermes' perspective it is a plain bring-your-own-key,
OpenAI-compatible provider: the user supplies ``OPENGATEWAY_API_KEY`` and
inference is routed through the gateway.

Registering this profile auto-wires the rest of the agent (same as the other
gateway profiles):
  - ``config.py`` surfaces OPENGATEWAY_API_KEY / OPENGATEWAY_BASE_URL in the
    webchat env editor (category="provider").
  - ``auth.py`` extends PROVIDER_REGISTRY so credential + base-URL resolution
    works for ``--provider opengateway``.
  - ``models.py`` / ``main.py`` route it through the generic api-key model
    picker, with live ``/models`` discovery falling back to ``fallback_models``.
"""

from providers import register_provider
from providers.base import ProviderProfile

opengateway = ProviderProfile(
    name="opengateway",
    aliases=("open-gateway",),
    display_name="OpenGateway",
    description="OpenGateway — gitlawb's open OpenAI-compatible LLM gateway",
    signup_url="https://opengateway.gitlawb.com",
    env_vars=("OPENGATEWAY_API_KEY", "OPENGATEWAY_BASE_URL"),
    base_url="https://opengateway.gitlawb.com/v1",
    auth_type="api_key",
    # Live /models discovery supersedes this whenever a key is present.
    fallback_models=("mimo-v2.5-pro",),
)

register_provider(opengateway)
