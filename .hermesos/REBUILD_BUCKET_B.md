# Lean Rebuild — Bucket B status

Stage 1: clean upstream + 336 additive files (Bucket A). +62543/-0, green.
Stage 2: invasive customizations re-applied onto the lean base, green-gated.

## ✅ DONE (backend — all re-applied + 118/118 custom tests green)
- managed-venice key fallback (hermes_cli/runtime_provider.py) — clean apply
- bankr config env aliases (hermes_cli/config.py, auth.py) — clean apply
- Venice toolset registration (toolsets.py) + image reference dispatch
  (tools/image_generation_tool.py) + media guidance (agent/prompt_builder.py,
  system_prompt.py) — clean apply
- approval_id (tools/approval.py) — clean apply
- runtime-governor wiring (gateway/run.py, gateway/platforms/api_server.py [5
  small conflicts resolved], cron/scheduler.py) — applied + green
- skills browsing for api_server (tools/skills_tool.py) — 1 conflict resolved
- cli.py provider-fallback + Dockerfile webchat bake — 1 conflict each, resolved

## ⏳ REMAINING (desktop frontend — TS, not backend-critical)
- admin-panel-nav (apps/desktop types.ts/sidebar/use-session-actions) — invasive TS
- Venice provider UI (apps/desktop settings constants + onboarding card) — invasive TS
These are frontend polish; the agent backend is fully functional without them.
Apply + validate against the full TS typecheck as the final pre-cutover step.

## Next: full-suite + typecheck + nix validation, then cutover to canary main.
