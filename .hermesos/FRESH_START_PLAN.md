# HermesOS Agent-Fork Fresh-Start Plan

**Repo:** `ashneil12/vanilla-hermes-agent-canary`
**Upstream:** `NousResearch/hermes-agent` (`upstream/main` = `d810f2b26…`, current diff base = merge-base `c7bfc938d`)
**Authored:** 2026-06-12
**Supersedes:** `.hermesos/customizations.yaml` (which declares only ~11 customizations / ~25 files) and `.hermesos/REBUILD_BUCKET_B.md` (stale point-in-time scaffolding).

This plan resets the fork to clean upstream and re-applies ONLY the customizations genuinely needed, with the chat/provider-resolution path re-derived so the keyless-provider brick class of bug cannot recur.

---

## 0. LOCKED SCOPE (2026-06-12, per Ash) — overrides the audit below

Branch from latest **`upstream/main` = `8b2a3c9c5`**. Principle: **stay as close to upstream as possible.**

**KEEP (re-apply on fresh upstream):**
- **Surplus** — clean plugin only (`plugins/model-providers/surplus/` + EnvPage line + test). NOT the auth.py hardcoded entry.
- **All Venice** — provider (plugin form) + media tools (image/video/tts/transcription/image_edit/extras/audio_generate/embed/multimodal/characters) + venice plugins + registries + managed-Venice surfacing.
- **Venice billing** — runtime-governor / managed-metering wiring (the one genuinely invasive piece; the hardest re-derivation).
- **Bankr wallet** — `optional-skills/bankr/` bundle + its ~6 gated wiring hooks + the bankr-gateway provider (wallet-funded inference). Off by default; lights up only when the dashboard provisions wallet creds.
- **Browser sidecar** (`tools/browser_sidecar.py`, Pro-tier gated).
- **Upload** — `/api/attachments/upload` + web-shim bridge + the 3 race/UX fixes.
- **Webchat surface glue** — web-shim token handoff (fixes the 401), `/webchat` mount, admin-panel nav, dash-bootstrap inject, dashboard↔chat theme sync.
- **Brand skin** (gold) — KEEP (vetoable; drop = vanilla upstream blue).
- **Health/egress probe** (`plugins/hermes-egress`) — KEEP (load-bearing: the fleet egress-sweep cron hits it).
- **Aeon delegation skill** (fork-only).
- **Signal setup skill + signal changes** (fixed real user problems).
- **Minimal brick protection only** — keyless-switch guard + `_switch_model_on_dead_session` (#96) + UI keyless-provider hide. (See design note.)
- **Build glue** — Dockerfile webchat bake, `.dockerignore` un-exclude, `.gitattributes`, `pyproject` (`webchat_dist` only), docker-publish pipeline, aeon-sync + tests-docs-noop workflows, nix-lockfile guards, `scripts/release.py` fork-identity AUTHOR_MAP (CI-required), accurate `customizations.yaml` rewrite.

**DROP:**
- **Credential-path guard** (`tools/file_tools.py` security) — per Ash; reverts to upstream default (agent may read secret files again).
- **Dead providers** — `crof`, `cometapi`, `ai-gateway` (empty dir; upstream deleted it).
- **Qwen overlay** — dashscope endpoint swap + `X-Stainless`/UA headers (auth.py/providers.py/run_agent.py) → revert to upstream Qwen.
- **Local audio skill EDITS** — heartmula/audiocraft are upstream-native; keep them VANILLA, drop our edits.
- **Memory plugin fixes** — honcho, hindsight.
- **Minor tweaks** — lossless context engine, skills source-tagging, approval-id targeting, gitignore-aware lister.
- **The heavy brick re-derivation** — public-host `OPENAI_API_KEY` resolution hack, the 5-aggregator hardcoded registry, per-turn re-resolution. Replaced by proper provider plugins (own env vars) + upstream-native managed-inference.

**DESIGN NOTE — why the brick fix shrinks:** the keyless brick was largely self-inflicted by the `OPENAI_API_KEY` + custom-`base_url` convention and the models-area surplus mess. On the fresh base, BYO providers are proper plugins (each declares its own env var) and **managed Venice is provisioned the upstream-native way (a `custom` provider with `key_env`)** — so sessions resolve cleanly and never fall to keyless `openai-api`. Only the small switch-guard + dead-session rescue remain as belt-and-suspenders. **Follow-up dependency (control plane / hermesdeploy):** managed-Venice provisioning must set `key_env` on a `custom` provider instead of the `OPENAI_API_KEY`+base_url hack. Verify upstream's `custom`+`key_env` handles managed Venice before relying on it.

---

## 1. EXECUTIVE SUMMARY

The current surface vs upstream base `c7bfc938d` is **439 files (+70,786/-1,425)** — but most of it is either (a) the single self-contained `optional-skills/bankr/` bundle (291 files), or (b) handlers that **upstream has since built itself** (its own dashboard chat backend, sessions/jobs/runs APIs) and we should now *take from upstream rather than re-apply*. The diff is large mostly because it was computed against a base that predates upstream's own webchat work.

After reconciling the verifiers, the minimal customization surface is:

| Verdict | Count (file-groups) | What it is |
|---|---|---|
| **KEEP_ESSENTIAL** (re-apply ~verbatim) | **~38** | additive bundles + a handful of trivial invasive list-entries |
| **RE_DERIVE_CLEANLY** (re-apply as clean additive layer) | **~30** | the invasive chat/provider/governor/media path |
| **UPSTREAM_NOW_COVERS** (take from upstream) | **~3** | sessions/chat backend handlers in `api_server.py`, `tests.yml`, `test_gui_uninstall.py` |
| **DROP** (dead / redundant) | **~2** | `REBUILD_BUCKET_B.md`, the `tests.yml` cosmetic diff |

**Headline:** the minimal base is roughly **~75–80 logical customizations across ~145 source files** (excluding the 290-file Bankr bundle which is a single zero-conflict additive drop). The *invasive* surface that actually needs careful re-derivation is **~30 files**, concentrated in two buckets: **provider-cli-core** (the brick fix) and **gateway-server-runtime** (the runtime-governor metering thread-through). Everything else is additive Venice/media tooling, plugins, skills, and CI that *never conflicts*. The 439-file number collapses to **~30 files of genuine merge risk** once the additive bundles and upstream-convergent handlers are accounted for.

### Reconciliation applied (verifiers are authoritative)

The verification pass **REFUTED one drop**:

- **`scripts/release.py`** — classifier said `DROP_REDUNDANT`. **REFUTED (high confidence).** Upgraded to **RE_DERIVE_CLEANLY**. The required PR gate `.github/workflows/contributor-check.yml` greps `scripts/release.py` for every non-merge commit-author email and **fails the required check** for any email not found in `AUTHOR_MAP`. Its skip-list exempts only `*teknium*|*noreply@github.com*|*dependabot*|*github-actions*|*anthropic.com*|*cursor.com*` and the `+…@users.noreply.github.com` pattern — it does **NOT** exempt `aeon@hermesos.cloud`, `ops@hermesos.cloud`, or `ashjeff33@gmail.com`. `aeon@hermesos.cloud` authored the entire lean-rebuild commit series. **Verified in-tree:** these aliases exist in our `release.py` (lines 71–75, 156) and the gate uses `grep -qF "\"${email}\""` against the file. A clean DROP would turn CI red on every fork PR. Correct action: take upstream's `release.py` base, then re-apply ONLY our ~6 fork-identity `AUTHOR_MAP` entries.

The other three verifications **confirmed** their verdicts (`tests.yml` drop, `REBUILD_BUCKET_B.md` drop, `test_gui_uninstall.py` drop) — all safe, with the note that the `tests.yml` "cosmetic" claim was wrong (it's a real but non-load-bearing save-durations merge fix worth re-porting if desired).

---

## 2. MINIMAL CUSTOMIZATION MANIFEST (supersedes `.hermesos/customizations.yaml`)

Ordered by re-apply phase. **A** = additive (never conflicts), **I** = invasive (edits an upstream-owned file). Difficulty: trivial / moderate / hard.

### Bucket A — Additive bundles (land first, zero merge risk)

| ID | A/I | Files | Intent | Verdict | Diff |
|---|---|---|---|---|---|
| `bankr-skill-bundle` | A | `optional-skills/bankr/**` (290) + `tests/hermes_cli/test_bankr_config_env.py` | Live Bankr onchain wallet skill payload; dormant until a wallet is provisioned | KEEP | trivial |
| `surplus-provider` | A | `plugins/model-providers/surplus/{__init__.py,plugin.yaml}` | BYOK Surplus Intelligence provider; auto-discovered by upstream's `plugins/model-providers/` scanner | KEEP | trivial |
| `venice-image-plugin` | A | `plugins/image_gen/venice/{__init__.py,plugin.yaml}` | Venice image backend the registry auto-pairs to | KEEP | trivial |
| `venice-video-plugin` | A | `plugins/video_gen/venice/{__init__.py,plugin.yaml}` | Venice video backend (Veo/Kling/Seedance/Wan) | KEEP | trivial |
| `venice-web-plugin` | A | `plugins/web/venice/{__init__.py,plugin.yaml,provider.py}` | Venice web search/scrape on shared key | KEEP | trivial |
| `venice-media-tools` | A | `tools/{image_edit_tool,venice_extras_tool,audio_generate_tool,embed_tool,multimodal_config_tool,venice_characters_tool}.py` | New self-registering Venice tools (image edit/compose/upscale, extras, audio, embed, multimodal cfg, characters) | KEEP | trivial |
| `media-local-skills` | A | `skills/media/heartmula/SKILL.md`, `skills/mlops/models/audiocraft/SKILL.md` | Local/offline audio synth skills that defer to the cloud `audio_generate` tool | KEEP | trivial |
| `health-egress-plugin` | A | `plugins/hermes-egress/dashboard/{plugin_api.py,manifest.json}` | Synthetic DNS+TCP egress probe consumed by the control-plane egress-sweep cron | KEEP | trivial |
| `browser-sidecar-tool` | A | `tools/browser_sidecar.py` | 11 Pro-tier Playwright primitives; `/health`-gated, inert on non-Pro boxes | KEEP | moderate |
| `aeon-delegation` | A | `skills/autonomous-ai-agents/aeon/**` (SKILL.md + 6 scripts) | Delegate recurring work to the user's GitHub-Actions Aeon fork | KEEP | trivial |
| `signal-setup-skill` | A | `skills/devops/signal-setup/SKILL.md` | Durable Signal (persisted JRE + signal-cli) runbook | KEEP | trivial |
| `lossless-context-engine` | A | `plugins/context_engine/lossless/{__init__.py,plugin.yaml}` | Opt-in lossless context compaction (V0 port); defer-or-revalidate | RE_DERIVE | moderate |
| `runtime-governor-module` | A (module) | `gateway/runtime_governor.py` | Stdlib HMAC client for the managed-metering sidecar; **module is additive, its wiring is invasive (Bucket D)** | KEEP (file) / RE_DERIVE (wiring) | trivial file / hard wiring |

### Bucket B — Provider/CLI core (the brick fix — invasive, re-derive as additive hooks)

| ID | A/I | Files | Intent | Verdict | Diff |
|---|---|---|---|---|---|
| `provider-aggregator-registry` | I | `hermes_cli/auth.py` | Register 5 OpenAI-compatible aggregators (venice/surplus/crof/bankr/cometapi) + add `no-key-required`/`no-key` to `_PLACEHOLDER_SECRET_VALUES`; Qwen dashscope endpoint + UA (re-validate) | RE_DERIVE | moderate |
| `public-host-key-resolution` | I | `hermes_cli/runtime_provider.py` | `_base_url_is_public_host()` + `reresolve_key_if_unusable_for_public_host()` + the public-host `OPENAI_API_KEY` candidate (the heart of the brick fix) | RE_DERIVE | moderate |
| `keyless-switch-guard` | I | `hermes_cli/model_switch.py` | `provider_has_resolvable_credentials()` + guard in `switch_model()` rejecting a switch to a keyless provider | RE_DERIVE | moderate |
| `bankr-env-bridge` | I | `hermes_cli/config.py` | `apply_bankr_env_from_config()` → `BANKR_*` env; consolidate to ONE hook | RE_DERIVE | moderate |
| `discovered-model-sort` | I | `hermes_cli/models.py` | `_sort_discovered_model_ids()` for navigable live catalogs (UX) | RE_DERIVE | trivial |
| `qwen-overlay-endpoint` | I | `hermes_cli/providers.py` | One-line Qwen `base_url_override` dashscope swap (lockstep with auth.py; re-validate, may DROP) | RE_DERIVE | trivial |

### Bucket C — Tooling registries & security (invasive list-entries + security guards)

| ID | A/I | Files | Intent | Verdict | Diff |
|---|---|---|---|---|---|
| `toolset-registration` | I | `toolsets.py`, `hermes_cli/tools_config.py` | Register browser_sidecar + crypto toolsets and Venice/multimodal tools in `_HERMES_CORE_TOOLS` / `CONFIGURABLE_TOOLSETS` (pure additive dict/list entries) | KEEP | trivial |
| `venice-media-registries` | I | `agent/{image_gen_registry,video_gen_registry,tts_registry,transcription_registry}.py` | VENICE_API_KEY auto-pair fallbacks + `venice` builtin names | RE_DERIVE | trivial |
| `venice-media-tool-bodies` | I | `tools/{image_generation_tool,video_generation_tool,tts_tool,transcription_tools}.py` | `MEDIA:` render-prefix steering (load-bearing for inline chat render), reference images, image→video coercion, Venice TTS/STT handlers + graceful fallback | RE_DERIVE | moderate |
| `credential-path-guard` | I | `tools/file_tools.py` | **SECURITY:** always-on block on reading/writing live-credential files (auth.json, id_rsa, ~/.ssh, ~/.aws, HERMES_HOME/.env). Re-derive as a small additive guard module | RE_DERIVE | moderate |
| `gitignore-aware-lister` | I | `tools/file_operations.py` | `rg --files` retry with `--no-ignore-vcs` + `note`; keeps `.ignore` honoured (skills-hub prompt-injection protection) | RE_DERIVE | moderate |
| `approval-id-targeting` | I | `tools/approval.py` | Stamp `approval_id`; resolve a specific queued gateway approval (re-derive on top of upstream's `allow_permanent`) | RE_DERIVE | moderate |
| `skills-source-tagging` | I | `tools/skills_tool.py`, `tools/skills_sync.py`, `tools/skills_hub.py` | bundled-vs-user skill tagging, cache-artifact-aware `_dir_hash`, frontmatter-name resolution | RE_DERIVE | moderate |
| `honcho-taskdone-fix` | I | `plugins/memory/honcho/session.py` | `task_done()` try/finally correctness fix (opt-in) — re-check upstream first | RE_DERIVE | trivial |
| `hindsight-keep-key` | I | `plugins/memory/hindsight/__init__.py` | "(blank to keep)" key-preserve UX (opt-in) — re-check upstream first | RE_DERIVE | trivial |

### Bucket D — Gateway/server runtime (the metering thread-through — highest merge risk)

| ID | A/I | Files | Intent | Verdict | Diff |
|---|---|---|---|---|---|
| `governor-wiring-gateway` | I | `gateway/run.py` | Thread admit/start/heartbeat/finish/fail around `_run_agent` + per-turn key re-resolution | RE_DERIVE | hard |
| `governor-wiring-apiserver` | I | `gateway/platforms/api_server.py` | **ONLY the governor wiring** onto upstream's own chat handlers; **take upstream's sessions/chat/jobs/runs handlers** (see Drop list) | RE_DERIVE | hard |
| `governor-wiring-cron` | I | `cron/scheduler.py` | Governor wrap of `run_job()` (cut off long crons mid-run) | RE_DERIVE | moderate |
| `cli-fallback-resolution` | I | `cli.py` | Re-apply only the fallback-provider chain + `reresolve_key_if_unusable_for_public_host` call onto upstream's `_ensure_runtime_credentials`/`_resolve_turn_agent_config` | RE_DERIVE | moderate |
| `dead-session-switch-rescue` | I | `tui_gateway/server.py` | `_switch_model_on_dead_session()` — switch AWAY from a broken provider agent-less (#96) | RE_DERIVE | moderate |
| `webchat-serve` | I/A | `hermes_cli/web_server.py` | `/webchat` mount (chat surface), `/api/status` dashboard_url, attachments/skills endpoints, surplus base_url adoption, max_models 50→1000 | RE_DERIVE | moderate |
| `qwen-portal-headers` | I | `run_agent.py` | Qwen UA/X-Stainless headers + bankr-prompt re-export imports | RE_DERIVE | moderate |
| `systemd-platform-guards` | I | `hermes_cli/gateway.py` | `sys.platform.startswith('linux')` guards (test/cross-platform safety) | RE_DERIVE | trivial |
| `agent-core-edits` | I | `agent/{agent_init,codex_runtime,chat_completion_helpers,conversation_loop,context_references,model_metadata,prompt_builder,system_prompt}.py` | Qwen headers, Venice character_slug, at-file auth.json block (security), context-length cache, media+bankr prompt wiring | KEEP/RE_DERIVE | trivial–moderate |

### Bucket E — Desktop / web UI surface (invasive but mostly small)

| ID | A/I | Files | Intent | Verdict | Diff |
|---|---|---|---|---|---|
| `webchat-web-shim` | A/I | `apps/desktop/src/lib/web-shim.ts`, `main.tsx`, `global.d.ts` | Browser bridge: token reader (iframe_token→hash, fixes 401), brand skin, dark seed, upload, openAdminPanel | KEEP | trivial |
| `admin-panel-nav` | I | `apps/desktop/src/app/{types.ts,chat/sidebar/index.tsx,session/hooks/use-session-actions.ts}` | Admin Panel + Settings sidebar items + action | KEEP/RE_DERIVE | trivial–moderate |
| `composer-upload` | I | `apps/desktop/src/app/chat/hooks/use-composer-actions.ts` | Web-shim drag-drop upload-then-attach | KEEP | moderate |
| `keyless-ui-guards` | I | `apps/desktop/src/app/shell/model-menu-panel.tsx`, `apps/desktop/src/components/model-picker.tsx`, `web/src/components/ModelPickerDialog.tsx` | Hide keyless (authenticated=false) providers from pickers (brick guard) | RE_DERIVE | moderate |
| `venice-recommended-surfacing` | I | `apps/desktop/src/app/settings/{constants.ts,providers-settings.tsx}`, `components/desktop-onboarding-overlay.{tsx,test.tsx}`, `types/hermes.ts` | Venice leads Settings; VeniceRecommendedCard managed-Venice deep-link | KEEP | trivial–moderate |
| `surplus-env-group` | I | `web/src/pages/EnvPage.tsx` | One PROVIDER_GROUPS line for Surplus | KEEP | trivial |
| `dashboard-theme-sync` | I | `apps/desktop/src/themes/context.tsx` | iframed dashboard→chat colorScheme postMessage sync | RE_DERIVE | moderate |
| `hermesos-brand-themes` | I | `apps/desktop/src/themes/presets.ts` | hivra/hermesOSDark BUILTIN_THEMES + DEFAULT_SKIN_NAME flip | KEEP | trivial |
| `dash-bootstrap-inject` | A | `web/inject-dash-bootstrap.cjs` | Splice base-path + token into `/dash` admin build | KEEP | trivial |

### Bucket F — Build / CI / packaging

| ID | A/I | Files | Intent | Verdict | Diff |
|---|---|---|---|---|---|
| `dockerfile-webchat-bake` | I | `Dockerfile` | webchat_build multi-stage (~21MB light bake), gh CLI, `/dash` build | RE_DERIVE | moderate |
| `dockerignore-unexclude` | I | `.dockerignore` | Un-exclude `apps/`/`tests/` so the webchat build context has source | KEEP | trivial |
| `gitattributes-merge-ours` | I | `.gitattributes` | `docker-publish.yml merge=ours` + `.gitattributes merge=union` | KEEP | trivial |
| `pyproject-webchat-data` | I | `pyproject.toml` | Add ONLY `webchat_dist/**/*` package-data; drop the 4 redundant plugin globs | RE_DERIVE | trivial |
| `docker-publish-pipeline` | I | `.github/workflows/docker-publish.yml` | Fork GHCR publisher + media-tool-wiring regression gate | KEEP | moderate |
| `aeon-sync-workflow` | A | `.github/workflows/aeon-sync.yml` | Autonomous upstream-sync (dispatch-only fallback) | KEEP | trivial |
| `tests-docs-noop` | A | `.github/workflows/tests-docs-noop.yml` | No-op companion fixing the docs-only required-context deadlock | KEEP | trivial |
| `nix-lockfile-guards` | I | `.github/workflows/nix-lockfile-fix.yml` | `if: env.APP_ID != ''` guards so the job skips cleanly | RE_DERIVE | trivial |
| `release-author-map` | I | `scripts/release.py` | **REFUTED→KEEP:** re-apply ~6 fork-identity AUTHOR_MAP entries (CI-required by contributor-check.yml) | RE_DERIVE | trivial |
| `aeon-docs` | A | `.hermesos/{customizations.yaml,AEON.md}` | Merge contract + design record (rewrite customizations.yaml accurate) | KEEP | moderate |

---

## 3. ORDERED REBUILD PLAN

Each phase ends with a **GATE** that must pass before proceeding.

### Phase 0 — Snapshot & branch
1. `rtk proxy git -C <repo> fetch upstream`
2. `rtk proxy git -C <repo> branch backup/pre-fresh-start origin/main` (escape hatch).
3. `rtk proxy git -C <repo> checkout -b lean-rebuild upstream/main` (clean upstream HEAD `d810f2b26…`).
- **GATE 0:** working tree is byte-identical to `upstream/main`; `pytest` baseline green on clean upstream.

### Phase 1 — Additive bundles (Bucket A, zero merge risk)
Copy each additive tree/file from `origin/main` verbatim:
1. `optional-skills/bankr/**` + `tests/hermes_cli/test_bankr_config_env.py`
2. All `plugins/{model-providers/surplus,image_gen/venice,video_gen/venice,web/venice,context_engine/lossless,hermes-egress/dashboard}/`
3. New `tools/*.py` additive files (image_edit, venice_extras, audio_generate, embed, multimodal_config, venice_characters, browser_sidecar)
4. `skills/{media,mlops,autonomous-ai-agents/aeon,devops/signal-setup}/**`
5. `gateway/runtime_governor.py` (module only; wiring comes in Phase 4)
- **GATE 1:** `python -c "import …"` for every new module; `pytest tests/providers tests/tools -q` green. These files cannot conflict by construction (new paths).

### Phase 2 — Provider/CLI core (Bucket B — the brick fix, FIRST invasive work)
Re-derive **additive-first** onto upstream's current files. Confirm upstream's candidate-list ordering in `runtime_provider.py` hasn't shifted (upstream rewrote this for #28660 and may again).
1. `hermes_cli/runtime_provider.py`: add `_base_url_is_public_host()` + `reresolve_key_if_unusable_for_public_host()` as **standalone helpers**; insert the single public-host `OPENAI_API_KEY` candidate at the two candidate-list sites with a clear comment.
2. `hermes_cli/auth.py`: prefer registering the 5 aggregators via the **existing auto-extend-from-config hook** rather than editing the dict literal; add `no-key-required`/`no-key` to `_PLACEHOLDER_SECRET_VALUES`; re-validate the Qwen dashscope swap + UA before re-applying.
3. `hermes_cli/model_switch.py`: drop `provider_has_resolvable_credentials()` in verbatim; re-insert the guard in `switch_model()` after model normalization.
4. `hermes_cli/{config,models,providers}.py`: bankr env hook (single call site), discovered-model sort, Qwen overlay (lockstep with auth.py).
- **GATE 2:** `pytest tests/hermes_cli/test_surplus_provider.py tests/hermes_cli/test_model_switch_custom_providers.py tests/providers/test_surplus_provider.py tests/hermes_cli/test_bankr_config_env.py -q` green. **Plus the brick regression test below (§5).**

### Phase 3 — Tooling registries, security, media bodies (Bucket C)
1. `toolsets.py` + `hermes_cli/tools_config.py`: re-add the toolset/tool list entries.
2. `agent/*_registry.py`: Venice auto-pair fallbacks + builtin names (verify upstream didn't already add `elevenlabs`).
3. `tools/{image_generation_tool,video_generation_tool,tts_tool,transcription_tools}.py`: MEDIA: steering + Venice handlers.
4. Security: `tools/file_tools.py` credential-path guard (as additive guard module), `tools/file_operations.py` lister.
5. `tools/approval.py` (on top of upstream `allow_permanent`), `tools/skills_*.py` source tagging.
6. `agent/*.py` core edits (security at-file block, context-length cache, media/bankr prompt wiring).
- **GATE 3:** `pytest tests/tools/test_media_generation_wiring.py -q` green (this is the same gate the docker-publish pipeline runs in-image). Tools surface in `hermes tools`.

### Phase 4 — Gateway/runtime governor + chat backend (Bucket D — hardest)
**Key principle: TAKE upstream's chat/session/jobs/runs handlers; re-thread ONLY the governor + key-re-resolution.**
1. `gateway/run.py`: thin governor hooks on upstream's current `_run_agent` + per-turn `reresolve_key_if_unusable_for_public_host`.
2. `gateway/platforms/api_server.py`: keep upstream's `_create_agent`/`_handle_*session*`/chat handlers; insert `_admit_runtime_governor`/`_runtime_heartbeat`/`_run_agent_with_runtime` into them. **Decide DROP for the detached-stream + memory/skills/config/available-models endpoints** unless a live consumer is re-confirmed (grep current surface).
3. `cron/scheduler.py`: governor wrap of `run_job()`.
4. `cli.py`: re-apply only the fallback chain + re-resolution call.
5. `tui_gateway/server.py`: `_switch_model_on_dead_session()` + handler branch.
6. `hermes_cli/web_server.py`: `/webchat` mount + `/api/status` dashboard_url + attachments/skills + surplus base_url + max_models.
7. `run_agent.py`, `hermes_cli/gateway.py`: Qwen headers / systemd guards.
- **GATE 4:** governor default-OFF (`HERMES_RUNTIME_GOVERNOR_*` unset) ⇒ non-managed agents behave exactly like upstream; `pytest` governor test files green; gateway boots and serves a chat turn locally.

### Phase 5 — UI surface (Bucket E)
Re-apply web-shim (verbatim), admin-panel-nav, the three keyless-UI picker guards (consolidate with the server-side guard from Phase 2), venice-recommended-surfacing, surplus env group, theme sync, brand themes, dash bootstrap.
- **GATE 5:** `npm test` (apps/desktop) green incl. the flipped `desktop-onboarding-overlay.test.tsx`; `vite build apps/desktop` succeeds.

### Phase 6 — Build / CI / packaging (Bucket F)
Re-apply Dockerfile webchat bake, `.dockerignore` un-exclude, `.gitattributes`, `pyproject.toml` (ONLY `webchat_dist/**/*`), docker-publish pipeline, aeon-sync + tests-docs-noop workflows, nix-lockfile guards, **and the `scripts/release.py` fork-identity AUTHOR_MAP entries (REFUTED — required by contributor-check.yml)**. Rewrite `.hermesos/customizations.yaml` to be accurate; drop `REBUILD_BUCKET_B.md`.
- **GATE 6 (CI-green):** open the lean-rebuild PR; **`contributor-check` must pass** (this is why release.py is non-negotiable); shards `test (1..6)` + `tests-docs-noop` green; docker-publish builds the image and the in-image media-tool-wiring gate passes.

### Phase 7 — Roll to test box & verify chat from clean base
1. Build/publish the image via `docker-publish.yml` (workflow_dispatch) to GHCR.
2. Roll to **pve10 VM1000** (canary test box) via the redeploy path.
3. **Verify chat end-to-end from the dashboard:** open webchat, send a turn, switch models (including to a BYOK/aggregator provider), confirm an image generates and renders inline (MEDIA: prefix), confirm no `Bearer no-key-required` 401, confirm a stored-model session resumes without bricking.
- **GATE 7:** chat works from the clean base; the brick scenario (§5) is non-reproducible.

### Phase 8 — Cutover
Fast-forward `main` to `lean-rebuild` (protection-dance + force-push as in prior rebuilds), keep `backup/pre-fresh-start` until the fleet has rolled clean for 48h.

---

## 4. DROP LIST (with proof)

| File / customization | Verdict | Proof |
|---|---|---|
| `.hermesos/REBUILD_BUCKET_B.md` | **DROP (dead)** | Transient status note from a prior rebuild run. Zero references anywhere (grep across repo = 0). Its one durable nugget (upstream rewrote desktop theming to per-profile skinPref/modePref; old global skin dropped → re-add brand skin as BUILTIN_THEME) is already implemented (`presets.ts` hivra/hermesOSDark) and recorded in `customizations.yaml`. **Verifier confirmed (high).** |
| `.github/workflows/tests.yml` (the diff) | **DROP (upstream covers)** | `paths-ignore [**/*.md, docs/**]` and `slice:[1..6]` matrix are **upstream's, verbatim**. Our only diff is a save-durations merge-step rewrite. **Verifier confirmed (medium)** — note: it IS a real (non-cosmetic) fix to duration-cache merging but never gates correctness, so taking upstream wholesale is safe. Re-port the recursive-glob fix later if duration-cache quality matters. |
| `tests/hermes_cli/test_gui_uninstall.py` (the diff) | **DROP (upstream covers)** | Our blob differs from base by **one trailing blank line**; upstream/main carries the identical-to-base blob. Code-under-test has zero fork diff. Take upstream's file. **Verifier confirmed (high).** |
| `scripts/release.py` | **~~DROP~~ → RE_DERIVE (REFUTED)** | **DO NOT DROP.** `contributor-check.yml` greps this file for every commit-author email and fails the required check otherwise; skip-list does NOT exempt `aeon@/ops@hermesos.cloud` or `ashjeff33@gmail.com`. Verified in-tree (entries at lines 71–75,156; gate uses `grep -qF`). Take upstream base, re-apply ~6 fork-identity AUTHOR_MAP entries. |
| `pyproject.toml` 4 plugin globs | **DROP (redundant subset)** | `*/plugin.yaml`, `*/plugin.yml`, `*/*/plugin.yaml`, `*/*/plugin.yml` are a strict subset of upstream's recursive `**/plugin.yaml`/`**/plugin.yml`. Keep ONLY `webchat_dist/**/*`. |
| `api_server.py` sessions/chat/jobs/runs handlers | **UPSTREAM NOW COVERS** | Upstream built its own dashboard chat backend after our base: `_create_agent`, `_handle_create/list/get/patch/delete_session`, `_handle_session_messages`, `_handle_fork_session`, `_handle_session_chat[_stream]` + routes. Take these from upstream; re-apply only the governor wiring. |
| `api_server.py` detached-stream + memory/skills/config/available-models endpoints | **DROP candidate (no live consumer)** | The shipped `apps/desktop` client doesn't reference the detached-stream (`/api/chat/stream` attach/snapshot/status/cancel) or these REST handlers (grep = 0; it uses upstream's chat path / web-shim bridge). **Re-confirm no consumer before dropping**; if confirmed, this is a superseded webui-compat layer. |
| `tests/hermes_cli/test_gui_uninstall.py` whitespace | covered above | — |

**No other verifier refutations.** Everything else flagged DROP in the classification either is dropped above with proof, or was never a drop.

---

## 5. CHAT / PROVIDER RE-DERIVATION (the bug epicenter)

**Root cause of the recurring live brick:** a session row stores a model with **no provider** → resolution falls to a keyless `openai-api` candidate → the sentinel `no-key-required` is sent as `Bearer` to a custom base_url → 401 / `Provider X is set but no API key was found` → agent init fails → **every model switch fails** (chicken-and-egg: you can't switch away from the broken provider).

The fix is layered across four seams. Re-derive each as **additive helpers + minimal insertion points**, NOT invasive interleaving into upstream's #28660-hardened candidate lists.

### Layer 1 — Resolution prefers an authed provider that serves the stored model
- `hermes_cli/runtime_provider.py`: keep `_base_url_is_public_host()` + `reresolve_key_if_unusable_for_public_host()` as standalone helpers. Insert ONE public-host `OPENAI_API_KEY` candidate at the two upstream candidate-list sites. This makes the HermesOS deploy convention (per-instance key in `OPENAI_API_KEY` paired with a custom `base_url` for venice/groq/bankr/managed-venice) resolve instead of falling to no-key-required. **Re-check upstream's current candidate ordering first.**
- `hermes_cli/auth.py`: add `no-key-required`/`no-key` to `_PLACEHOLDER_SECRET_VALUES` so the sentinel **never preempts a real env key**. Register the 5 aggregators via the auto-extend hook so `resolve_provider_client('venice'|…)` finds a base_url+key.

### Layer 2 — The switch guard (can't pick a keyless provider)
- `hermes_cli/model_switch.py`: `provider_has_resolvable_credentials()` + a guard in `switch_model()` that **rejects** rewriting `config.yaml` to a provider with no resolvable key. This prevents the picker from ever creating the bricking state.

### Layer 3 — Per-turn re-resolution (transient empty-key window)
- `gateway/run.py` + `cli.py`: per-turn `reresolve_key_if_unusable_for_public_host` so a momentarily-empty `~/.hermes/.env` (during a dashboard rewrite) never goes out as `Bearer no-key-required`. `cli.py` also walks `_fallback_model` on `AuthError` (authed-provider fallback chain).

### Layer 4 — Dead-session rescue + UI guards (defence in depth)
- `tui_gateway/server.py`: `_switch_model_on_dead_session()` validates the TARGET provider's creds agent-less, resets the build latch, rebuilds — breaking the chicken-and-egg.
- Picker guards (`model-menu-panel.tsx`, `model-picker.tsx`, `web/ModelPickerDialog.tsx`): hide `authenticated=false` providers so a keyless pick is never offered. **Consolidate** these three client guards with the **server-side** Layer-2 guard so correctness lives server-side and the UI is merely cosmetic — preferably surface the same `authenticated` flag from one place (e.g. `available-models`/`model.options`).

### Why this class can't recur on the fresh base
- The **sentinel can never preempt a real key** (Layer 1 placeholder set).
- The **switch can never write a keyless provider into config** (Layer 2 guard).
- A **transient empty key self-heals per turn** (Layer 3).
- If a broken state is somehow reached, you can **always switch away** (Layer 4 rescue) and the UI never offers a keyless pick.
- All four are **additive helpers + single-line insertions**, so an upstream sync can't silently un-do them, and `customizations.yaml` will declare each (closing the "undeclared = clobberable" gap).

**Regression test (add to an EXISTING on-main test file, never a net-new file — avoids the shard-3 wipe trap):** a session row with a stored model and empty provider, with only a custom-base_url key set, must (a) resolve to the authed provider, (b) NOT send `no-key-required`, (c) allow a model switch to succeed.

---

## 6. RISKS & OPEN QUESTIONS

1. **Upstream rewrote `runtime_provider.py` for #28660 and may again.** The two candidate-list insertion sites are the single most fragile re-derivation. Re-read upstream's current ordering before inserting; pin a test that asserts the public-host candidate is present.
2. **`api_server.py` detached-stream surface — confirm-or-drop.** Must grep the *current* `apps/desktop` + web surface for any consumer before dropping the detached-stream/memory/skills/config endpoints. If a Hivra/control-plane caller exists, it becomes RE_DERIVE not DROP.
3. **Governor wiring is the chief merge-pain.** Three large invasive insertions (`run.py`, `api_server.py`, `cron/scheduler.py`) onto upstream methods that may have been restructured. Mitigate by keeping each hook to ≤5 lines around upstream's call sites and asserting default-OFF behavior.
4. **`scripts/release.py` must ship with fork-identity entries or CI is red.** Non-negotiable per the refutation; also `scripts/contributor_audit.py` imports `AUTHOR_MAP`. Add the entries in the SAME PR.
5. **Qwen dashscope endpoint + UA spoof may be obsolete.** Re-validate `portal.qwen.ai` against current upstream Qwen OAuth before re-applying the `auth.py`/`providers.py`/`run_agent.py` Qwen changes — DROP if `portal.qwen.ai` works now.
6. **`.dockerignore` un-exclude grows build context** (un-ignores nix/tests). Acceptable, but prefer the cleaner `!apps/` form over deleting upstream's exclusion block so future upstream additions to the ignore list aren't lost.
7. **Brand skin vs upstream per-profile theming.** Upstream moved to per-profile `skinPref/modePref`; the brand skin is now a BUILTIN_THEME + web-shim `installBrandSkin()`. Verify the `DEFAULT_SKIN_NAME` flip still takes effect on upstream's current theme resolver.
8. **`customizations.yaml` accuracy is itself a deliverable.** Today it declares ~11/~25; the fresh tree must declare every re-applied invasive customization or the next autonomous sync can clobber the brick fix. Treat the manifest rewrite as a Phase-6 gate item.
9. **Shard-3 net-new-test wipe trap.** The brick regression test (and any new test) must fold into an existing on-main test file, not a net-new `test_*.py`, or it deterministically fails `test (3)`.
10. **`lossless-context-engine` and the two opt-in memory plugin fixes** are low-value; safe to defer entirely if trimming surface area — re-validate against upstream's current ContextEngine seam if kept.
