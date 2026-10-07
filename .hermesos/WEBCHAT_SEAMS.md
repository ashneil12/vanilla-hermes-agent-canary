# Webchat / Desktop-web / dashboard seams (fork delta on v2026.9.24)

Every edit of an upstream-owned file carries `hermes-fork: <seam>` on or above the changed block.
Find them all: `git grep -n "hermes-fork:" -- apps web hermes_cli Dockerfile .dockerignore`.

## Marked patches in upstream-owned files

| Seam | File(s) | Lines | Why it must stay |
|---|---|---|---|
| `web-shim` | `apps/desktop/src/main.tsx` | +3 | Installs the browser `window.hermesDesktop` before anything reads it. No-op under Electron. |
| `web-file-picker` | `app/chat/composer/context-menu.tsx`, `composer/index.tsx` | +24 / +5 | The composer "+" Files/Images rows cannot open the native chooser from Radix `onSelect` inside the cross-origin iframe (no transient user activation). Hidden inputs are clicked from a real DOM `onClick`. Logic lives in fork-only `web-file-picker.tsx`. |
| `venice-card` | `components/onboarding/index.tsx`, `providers.tsx`, `app/settings/providers-settings.tsx` | +15 / +4 / +4 | Managed-Venice recommended card (onboarding + Settings > Providers), Venice first in the key list, and the generic "Recommended" pill hidden when the card holds the slot. Logic in fork-only `venice-recommended-card.tsx`. |
| `keyless-provider-guard` | `components/model-picker.tsx`, `app/shell/model-catalog-menu.tsx` | +7 / +7 | Chat pickers hide `authenticated === false` providers. Cosmetic: the server already rejects a keyless switch (`tests/hermes_cli/test_fork_core_seams.py`). Drop both if upstream's picker UX starts to conflict. |
| `hivra-web` | `hermes_cli/web_server.py` | +4 | Mounts the fork-only router, beside `mount_spa`. |
| `hivra-web-build` | `Dockerfile` | +25 top stage, +5 COPY | Self-contained `hivra_web_build` stage FIRST in the file (webchat `--base=/webchat/` + dashboard `--base=/dash/` + `inject-dash-bootstrap.cjs`), one `COPY --from` in the runtime stage after the gh-cli block. |
| `hivra-web-build` | `.dockerignore` | +4 | Keeps `apps/desktop` in the build context. |

## Fork-only files (never edited upstream)

- `apps/desktop/src/lib/web-shim.ts`, `web-files.ts`, `web-terminal.ts` (+ tests): the browser bridge, attachments (synthetic paths), browser terminal over the Hivra sidecar.
- `apps/desktop/src/plugins/hivra/` (bundled plugin, auto-registered by upstream's vite glob, inert unless `window.__HERMES_WEB_CLIENT__`): Hivra theme (+ first-run default; the old `hermesos-dark` alias is gone), Admin Panel sidebar row and route page, dashboard appearance / starter-prompt `postMessage` bridge, phone polish (dvh, 16px inputs, safe-area, viewport-fit, close overlays on navigation).
- `apps/desktop/src/lib/web-shim-drift.test.ts`: CI drift guard (see Re-sync).
- `hermes_cli/web_routers/fork_hivra.py`: `GET /api/hivra/config` -> `{dashboard_url}`.
- `web/inject-dash-bootstrap.cjs`.
- Tests: `tests/hermes_cli/test_web_server_fork_hivra.py`, `*.keyless.test.tsx`, `web-shim*.test.ts`, `src/contrib/hivra-plugin.test.tsx` (bundled-plugin tests live in `src/contrib/`; the plugin lint rule allows only the SDK inside `plugins/`), `venice-recommended-card.test.tsx`, `web-file-picker.test.tsx`. One upstream test narrowed: `components/onboarding/index.test.tsx` (the Venice card holds the Recommended slot).

## Dropped (upstream does it, or no longer needed)

`use-gateway-boot` first-handshake retry + `GatewayTransportError` in `apps/shared` (upstream retries a failed remote dial, `stage === 'dialing'`) · `gateway-ws-url.ts` · `use-composer-actions` / `use-prompt-actions` upload hunks and `POST /api/attachments/upload` (~130 py lines) · gold `installBrandSkin()` and `seedDefaultColorMode` · `themes/presets.ts`, `themes/context.tsx`, `wiring.tsx`, `sidebar/index.tsx`, `types.ts`, `use-session-actions` hunks (now the plugin) · About / update-banner removal (managed boxes report `can_apply:false`) · backup list/download UI and 3 py hunks · `/webchat` Python mount · `ModelAssignment`/`Moa*` classes · `HERMES_DASHBOARD_TRUST_PROXY` · `/api/media` `/workspace` root (the renderer reads media through `/api/fs/read-data-url`) · `_provider_profile_base_url` (`switch_model` resolves the profile endpoint) · `_gateway_health_api_key` · `_fs_default_cwd` hunk (config) · Backdrop.tsx · `touch:` variant patches in ~14 files (upstream trusts `:hover`, so a tap reveals; replaced by `plugins/hivra/web.css`) · `overlay-search-input.tsx` (orphan) · EnvPage `SURPLUS_` group, settings `PROVIDER_GROUPS` Venice/Surplus/Bankr rows · web `ModelPickerDialog` filter.

## Hivra control plane must provide (do not edit from here)

- `terminal.cwd: /workspace` in the box's config.yaml, or the file tree opens at the dashboard's launch dir. `TERMINAL_CWD=/workspace` on the dashboard env is NOT enough (the config default `"."` wins in `_fs_default_cwd`). The sidecar already sets `TERMINAL_CWD` for itself only.
- `HERMES_DASHBOARD_URL` on the dashboard service (already in the box `.env`) for the Venice deep link.
- Box install stamp `/opt/hermes/.install_method = docker` (the image bakes it) so no "Update ready" toast / About update UI appears. Reproduced locally with the stamp.

## Re-sync checklist

1. `cd apps/desktop && npx vitest run src/lib/web-shim-drift.test.ts`. A new REQUIRED preload key: implement it in `web-shim.ts` or add it to `ACKNOWLEDGED_ABSENT`. Never add a catch-all no-op Proxy: the renderer feature-detects Electron-only UI (`?.cloud`, `typeof openWindow === 'function'`), a no-op would switch it on.
2. `npx vite build --base=/webchat/ --outDir /tmp/x` and `cd web && npx vite build --base=/dash/ --outDir /tmp/y && node inject-dash-bootstrap.cjs /tmp/y/index.html`.
3. Upstream restructures the Dockerfile often (stages `runtime_base`, `frontend_build` already on `upstream/main`, web built by `scripts/build/web.mjs` with generated icons): the `/dash` build here is a plain `vite build`; re-check favicon/icons there.
4. `src/contrib/hivra-plugin.test.tsx` fails if the theme provider's storage key or default-skin resolution changes.
