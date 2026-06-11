# Lean Rebuild — Bucket B (invasive, deferred from Stage 1)

Stage 1 = clean upstream + Bucket A (additive files only), green.
Bucket B = the invasive customizations that edit upstream files. Re-apply ONE
subsystem at a time, ideally restructured to be ADDITIVE (own file / hook), each
green-gated. Its deferred tests come back WITH it.

| Subsystem | Invasive surface (upstream files edited) | Deferred test | Restructure-to-additive idea |
|---|---|---|---|
| runtime-governor wiring | gateway/run.py, gateway/platforms/api_server.py (admit/heartbeat/finish) | tests/gateway/test_runtime_governor.py | middleware/hook around the run loop |
| approval_id | tools/approval.py, api_server /approve | tests/gateway/test_api_server_approvals.py | additive approval registry keyed by id |
| managed-venice key fallback | hermes_cli/runtime_provider.py | tests/hermes_cli/test_no_key_required_placeholder.py | wrap resolve in our own resolver module |
| bankr config env aliases | hermes_cli config load/save | tests/hermes_cli/test_bankr_config_env.py | post-load env hook |
| Venice toolset registration | toolsets.py | tests/tools/test_media_generation_wiring.py | plugin-style tool auto-register |
| image reference dispatch | tools/image_generation_tool.py | tests/tools/test_image_edit_model_resolution.py | route via our image_edit_tool, not edit upstream's |
| desktop admin-panel-nav | apps/desktop types.ts/sidebar/use-session-actions | (TS) | upstream extension point if any |
| Venice provider UI | apps/desktop settings constants + onboarding | (TS) | additive card component |
| Dockerfile webchat bake | Dockerfile | tests/tools/test_docker_entrypoint_permissions.py (passes — additive) | keep as a declared block |
| cli.py provider-fallback | cli.py | — | additive fallback wrapper |
