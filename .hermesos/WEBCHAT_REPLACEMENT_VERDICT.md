<!-- Written 2026-10-07 for the thinning of this fork onto upstream v2026.9.24. Evidence is code read at pinned refs; UNVERIFIED items are listed in section 10. -->
# Webchat shim vs upstream dashboard / Desktop remote: verdict

Read-only research, 2026-10-07. Refs: fork `canary/main` a9443cb610 (upstream base 3bdc2165, 2026-08-22, v0.20.5-era), `origin/main` 19a8154095,
upstream tag `v2026.9.24` (v0.21.5, f97608f178), `upstream/main` 808520532c. Hivra side: `Hivra-public-canary` checkout.
Cites are `path@ref`. UNVERIFIED = not proven by code I read and not tested live. I touched no box, DB or checkout.

## 0. Headline findings

1. **Upstream has no browser build of the Desktop renderer.** `apps/desktop` needs `window.hermesDesktop` (the Electron preload). The
   fork's `web-shim.ts` installs that global in a browser. Nothing at v2026.9.24 or upstream/main replaces it (grep for web/browser
   bridge, `__HERMES_WEB*`, `installWeb*`: no hits; the only `-desktop` Docker tag is Bot Screen VNC, `Dockerfile@v2026.9.24:76-90`).
2. **Upstream dashboard "Chat" is `hermes --tui` inside xterm.js over `/api/pty`**, not a rich chat (`web/src/pages/ChatPage.tsx@v2026.9.24:1-15`).
   It has a session switcher (`ChatSessionList.tsx`), a status sidebar, an image-only paste upload (`/api/chat/image-upload`) and workspace picker.
   It has no message-level UI, attachments chip UI, or Desktop settings. It already exists at `/dash/chat` on Hivra boxes (`HERMES_DASHBOARD_TUI=1`).
   It cannot replace the iframe chat. It is a different product surface.
3. **Fork vs upstream scope.** Fork `apps/desktop`+`apps/shared`+`web` delta vs merge-base: 75 files, +3829/-377. Not one file under
   `apps/desktop/electron/` is changed, so the native Desktop app is untouched by the fork. Every fork `apps/desktop` change is web-only or Hivra product UX.
4. **Drift is already large.** The preload bridge grew from ~120 to ~145 keys between 3bdc2165 and v2026.9.24 (+25 new). The shim implements ~52
   (my count of 4-space keys). ~102 bridge keys are absent from the shim; ~20 of those are called without `?.` in non-test renderer code
   (e.g. `oauthLoginConnectionConfig`, `glassSupported`, `zoom`, `quickEntry`, `getConnectionFor`). Static count only; some sit behind Electron-only UI. UNVERIFIED which crash at runtime.
5. **Contract file is wrong about the router.** `webfree-contract.md` row 13 says Desktop Web uses a "root-level browser-history router".
   Both `canary/main`, `origin/main` and `v2026.9.24` mount `HashRouter` (`apps/desktop/src/main.tsx`), and the only `pathname` use is the shim's own `replaceState`. Row 13 (`@hermesDesktopDocument`) is probably a harmless safety net, not load-bearing. Keep it until a live probe confirms; correct the contract.
6. **Native Desktop sign-in likely does not complete against `/desktop` today (UNVERIFIED, highest-value check).** See table 7.

## 1. Auth / token bootstrap

Hivra need: one per-box key (API_SERVER_KEY = HERMES_DASHBOARD_SESSION_TOKEN = basic-auth password); sidecar logs in, mints ws-tickets; never TRUST_PROXY; no key in a server-visible request line where avoidable.

| Aspect | Fork shim today | Upstream today | Verdict | Blocks replacement | Effort |
|---|---|---|---|---|---|
| Token read from `#iframe_token`/`#token`, sessionStorage, strip from URL | `web-shim.ts resolveConfig()` (hash > `__HERMES_SESSION_TOKEN__` > `__HERMES_WEB_TOKEN__` > sessionStorage) | Dashboard SPA only reads server-injected `__HERMES_SESSION_TOKEN__` (`web_server_dashboard.py@v2026.9.24:152-170`); none when gated. Desktop reads tokens in Electron main | **KEEP-AS-SEAM** | No upstream hash-token reader for a browser renderer | 0 (already add-only file) |
| REST auth | `Authorization: Bearer <key>`, `credentials:'omit'` to `/desktop/api/*`; Caddy `@desktopBearer` then sidecar then gated cookie | Dashboard SPA uses `X-Hermes-Session-Token` or cookie (`web/src/lib/api.ts`); gated mode = cookie (`SameSite=Lax`, `dashboard_auth/cookies.py:60`) | **KEEP-AS-SEAM** | Lax cookies do not flow in the cross-site iframe | 0 |
| WS auth | `wss://<box>/desktop/api/ws?token=<long-lived key>`; sidecar mints dashboard ticket (`sidecar-script.ts:2079-2101, 2257-2275`) | Gated gateway accepts `?ticket=` or subprotocol `hermes-gateway-ticket.<t>`; `?token=` rejected when gated (`web_server_chat.py@v2026.9.24:206-285`) | **KEEP-AS-SEAM** (improve) | Still works: sidecar uses `?ticket=` which 0.21.5 accepts | M (optional hardening below) |
| Long-lived key in WS query string | present (`buildUrls`) and in Caddy `@desktopQueryToken` | Upstream pattern is a ticket minted by authenticated POST | PARTIAL | Needs sidecar route `POST /desktop/api/auth/ws-ticket` (bearer) + a Caddy ticket matcher; UNVERIFIED the sidecar proxy already passes that POST | M, optional, security win |
| `getGatewayWsUrl` re-mint (`gateway-ws-url.ts`, 91 lines) | stale fork copy | Upstream moved `resolveGatewayWsUrl` to `@hermes/shared`; token mode falls back to `conn.wsUrl` when no mint bridge (`apps/desktop/src/lib/gateway-ws-url.ts@v2026.9.24`) | **REPLACE** (drop file on sync) | none | S |
| `HERMES_DASHBOARD_TRUST_PROXY` patch (`web_server.py` +11) | dead | not upstream; Hivra never sets it (`webui-instance-builder.ts:1740` says so) | **REPLACE** (delete) | none | S |

## 2. Iframe embedding

Hivra iframes only `/webchat` (`components/webui/WebuiIframe.tsx:1300`, `sandbox="allow-scripts allow-same-origin allow-forms allow-popups ..."`). Admin Panel opens in a new top-level tab via `window.open('/dash/#iframe_token=...')`.

| Aspect | Fork today | Upstream today | Verdict | Blocks | Effort |
|---|---|---|---|---|---|
| Frame headers | Caddy strips `X-Frame-Options`, sets CSP `frame-ancestors` allowlist (`webui-instance-builder.ts:2054-2063`) | Upstream sets neither header (grep of `hermes_cli@v2026.9.24`: no X-Frame-Options/frame-ancestors) | **KEEP-AS-SEAM** (Caddy, not fork) | Upstream will not frame-protect or frame-allow; Caddy owns it. No code change needed | 0 |
| Cookies in 3rd-party iframe | Hash bearer, no cookie dependence for chat API; sidecar cookie `hermes_webui_session` is `SameSite=None; Secure` (`sidecar-script.ts:4300`) | Gate cookies `SameSite=Lax` except PKCE cookie (`cookies.py:60-71`). hivra.cloud vs hermesos.cloud are cross-site, so Lax cookies would not be sent | **KEEP-AS-SEAM** | Upstream dashboard SPA (gated) cannot self-auth inside a cross-site frame | 0 |
| File picker inside iframe | `selectBrowserFiles` + persistent hidden `<input>` clicked from a real DOM gesture (`context-menu.tsx` +90, `use-composer-actions.ts`) | Electron IPC `selectPaths`; no iframe concept | **KEEP-AS-SEAM** | Radix `onSelect` loses user activation in a cross-origin frame (fork comment, commit 3931523d10) | 0 (patch stays, ~1 core hunk) |
| Dashboard to frame messages | `hermes-dashboard:appearance` (`themes/context.tsx`), `hermes-dashboard:send-message` (`use-dashboard-bridge.ts`, 61 lines; Hivra callers `WorkflowsPanel.tsx`, `WebuiIframe.tsx`, `webui-appearance.ts`) | none; plugin SDK exports `useTheme`, `requestTheme`, gateway request helpers but no documented "submit as user" call (UNVERIFIED) | **KEEP-AS-SEAM** | First-usage stamping depends on `submitText` creating the session | S to M if moved into a plugin |

## 3. Theming / brand skin

Hivra changes (fork): `themes/presets.ts` +80 (`hivra` red dual-mode theme, `hermesos-dark`, `DEFAULT_SKIN_NAME='hivra'`), `themes/context.tsx` +61 (`?theme=` boot hint, appearance postMessage), `styles.css` +55 (touch variant/layer, not branding), shim `installBrandSkin()` (GOLD `!important` overrides) and `seedDefaultColorMode()`, `web/src/components/Backdrop.tsx` (137 lines).

| Piece | Upstream capability (v2026.9.24) | Verdict | What blocks / note | Effort |
|---|---|---|---|---|
| Brand palette in Desktop renderer | Theme registry areas: `THEMES_AREA` (`themes/user-themes.ts:132`) accepts a `DesktopTheme` as a data contribution from a bundled plugin; bundled plugins are auto-registered by vite glob `src/plugins/*/plugin.{js,ts,tsx}` (`contrib/plugins.ts`); also backend skins from `$HERMES_HOME/skins/*.yaml` but those are single-mode (`themes/skin.ts`) so lose light/dark pairing | **REPLACE** presets.ts patch with an add-only plugin file | `DEFAULT_SKIN_NAME` is a constant (`'nous'`); first-run default must be seeded in the shim (same pattern as `seedDefaultColorMode`) or via `requestTheme`/`setTheme` from the plugin. UNVERIFIED that a contributed theme can be the boot default before first paint | S |
| `?theme=`/appearance sync | none | **KEEP-AS-SEAM** | Only the `readDashboardModeFromUrl` + message listener (~40 lines) is real; could move into the plugin with `useTheme().setMode` (UNVERIFIED) | S |
| `installBrandSkin()` GOLD overrides | n/a | **drop** | It re-tints `--theme-primary`, `--ui-accent`, `--ui-blue` with `!important`; the renderer paints these inline (`context.tsx` comment about inline overrides), so gold likely beats the red `hivra` skin. Likely stale conflict (UNVERIFIED visually). Delete or reconcile before the next sync | S |
| `Backdrop.tsx` | `web/src/components/Backdrop.tsx` does not exist upstream; fork copy is imported nowhere (only `ChatPage.test.tsx` mocks it; `git grep Backdrop canary/main -- web/src`) | **REPLACE** (delete now) | none; dead file | S |
| Admin Panel theme (`/dash`) | Dashboard themes: built-ins + YAML in dashboard themes dir via `/api/dashboard/theme` (`web_server_dashboard.py@v2026.9.24:~245+`); plugin slots in `web/src/plugins` | **REPLACE** (no fork change needed) | Fork changes nothing visible in `/dash` except EnvPage line + ModelPicker filter. Seed a theme YAML via the control plane if branding wanted | S |

## 4. Terminal

| Hivra need | Fork shim today | Upstream today | Verdict | Blocks | Effort |
|---|---|---|---|---|---|
| Rail terminal for a remote box in the browser | `web-terminal.ts` (690 lines, + 724 test) talks to sidecar `POST /api/desktop-terminal` and `/_sidecar/api/terminal/ws` (scoped, ticketed, gateway-container only; `sidecar-script.ts:1447-1585, 4103-4125`) | HTTP remote gateways: none. Desktop's remote terminal is SSH-only "interim until dashboard /api/terminal lands" (`ssh-connection.ts@v2026.9.24:298-303`); `grep /api/terminal hermes_cli` at tag and upstream/main: no route. Dashboard `/api/pty` runs the TUI, not a shell | **KEEP-AS-SEAM** | Hivra-specific sidecar protocol; no upstream equivalent | 0; keep add-only (`web-terminal.ts` is new, only 2 lines in `rail.tsx`) |
| Admin Panel terminal | Upstream `/dash` Chat (TUI) already available | n/a | **REPLACE** n/a | | |

## 5. Chat feature parity

Left column = what Hivra users get in the iframe chat (the Desktop renderer). Right = what upstream dashboard Chat/pages provide.

| Feature | Fork shim / patches | Upstream dashboard (v2026.9.24) | Verdict | Note | Effort |
|---|---|---|---|---|---|
| Rich message UI, tool cards, markdown, media | Desktop renderer (upstream code) | TUI text in xterm | **KEEP** (renderer) | Cannot be replaced by `/dash/chat` | n/a |
| Sessions list / switcher | Desktop sidebar (upstream) | `ChatSessionList` + Sessions page (search/export/import/delete) | n/a | Upstream page is the better admin tool; link it | 0 |
| Attachments upload | `POST /api/attachments/upload` (`web_server.py`, ~130 py lines incl. helpers; chown to HERMES_HOME owner) + shim `uploadFile`/`selectPaths` | `POST /api/files/upload` (base64, path chosen by client, managed root policy) and `/api/chat/image-upload` (images only) (`web_routers/files.py@v2026.9.24:330-345, 501-508`) | **PARTIAL** | Switch shim to `/api/files/upload` and set `HERMES_DASHBOARD_FILES_ROOT=/workspace` (`web_server_files.py:12`, upstream env, no patch). Unknown: upload size cap vs 50 MB fork cap, body-limit middleware (`dashboard_auth/body_limit.py`), file ownership (dashboard now runs uid 1024, so the chown rationale is gone). Only the shim calls `/api/attachments/upload` (grep of Hivra `src`: manifest only) | M |
| File tree (project/right rail) | `use-project-tree.ts` remote-cwd fallback (+26) via `desktopDefaultCwd`; `_fs_default_cwd` /workspace-first (+17 py) | `_fs_default_cwd` honors `terminal.cwd` / `TERMINAL_CWD` (`web_routers/files.py:205-215`) | **PARTIAL** | Set `TERMINAL_CWD=/workspace` on the dashboard env and drop the py hunk; the JS hunk may also go (UNVERIFIED) | S |
| `/api/media` roots incl. `/workspace` | `_media_serve_roots` +1 root | upstream roots are images/screenshots/cache only | **KEEP-AS-SEAM** | Not configurable upstream; keep as a 1-line py patch | S |
| Slash commands, model picker | Desktop renderer + `ModelPickerDialog`/`model-picker.tsx` "authenticated" filter (brick guard) | TUI slash commands; web `ModelPickerDialog` | **KEEP-AS-SEAM** | Filter is product safety (keyless provider), tiny hunks. Revisit after upstream resync; may already be upstream | S |
| Onboarding | `components/onboarding/index.tsx` +82 (Venice-recommended card, `dashboard_url`) + `status.dashboard_url` (+3 py) | none (Hivra-specific) | **KEEP-AS-SEAM** | Product feature, not a shim concern | M |
| Update banners / self-update UI | `about-settings.tsx` (-148), `store/updates.ts` (-72) remove update UI | Backend `can_apply = (install_method=="git")` (`web_routers/actions.py:279`) feeds `supported`; containers are "managed externally" (`web_server_files.py:100-115`); About page honors `supported` (`about-settings.tsx@v2026.9.24:90-102`) | **REPLACE** (likely) | Verify one render of About + the skew toast with `can_apply:false`, then drop both patches | S |
| Gateway restart | Sidecar `handleManagedGatewayAction` at `/desktop/api/gateway/restart` (Hivra, not fork) | upstream `POST /api/gateway/restart` (shadow-gateway risk, see contract section 5) | **KEEP-AS-SEAM** (Hivra sidecar) | No fork change involved | 0 |
| Composer context menu (iframe picker) | `context-menu.tsx` +90 | n/a | **KEEP-AS-SEAM** | See table 2 | 0 |
| Backup list/download | `maintenance.tsx` +38, `api/system.ts` +40, `/api/ops/backups` GET (+30 py), `_QUERY_TOKEN_API_PATHS` += backup download | Upstream has `POST /api/ops/backup` and `GET /api/ops/backup/download?archive=` (`web/src/lib/api.ts:1321-1328`), but not list, and `?token=` auth only for `/api/files/download` | **PARTIAL** | Admin Panel covers backup; drop this Desktop UI + 3 py hunks unless users need it in the chat shell | S |
| Gateway health bearer (`_gateway_health_api_key`, +40 py) | probe adds `Authorization` for `/health/detailed` | Upstream probe is unauthenticated and falls back to `/health` (`web_server_gateway.py@v2026.9.24:23-40`) | PARTIAL | Likely droppable; UNVERIFIED effect on `/api/status.gateway_state` on Hivra boxes (gateway `/health/detailed` is Bearer-gated) | S |
| Reverse: upstream-only features | Admin Panel `/dash`: Files page (upload/download/mkdir), Sessions mgmt, Cron, Skills, Logs, Analytics, Profiles, Plugins, MCP, System/Maintenance | | n/a | Already reachable via Admin Panel. Do not rebuild in the shim | 0 |

## 6. Routing under Hivra's inner Caddy

| Route | Fork today | Would upstream pages work there? | Verdict | Evidence / gap | Effort |
|---|---|---|---|---|---|
| `/` and `/webchat*` (webchat bundle) | Vite `--base=/webchat/` absolute assets; `try_files {path} /index.html`; Hash router (see 0.5) | Upstream `apps/desktop/vite.config.ts` has `base: './'` (relative). At `/` (the `@hermesRoot` rule) relative asset URLs would resolve to `/assets/*`, which `@public` sends to official-dashboard (wrong bundle) | **KEEP-AS-SEAM** | Absolute base is required; keep the Dockerfile flag | 0 |
| `/dash*` static bundle (`web_dist_dash`) | Second `vite build --base=/dash/` + `inject-dash-bootstrap.cjs` (49 lines) sets `__HERMES_BASE_PATH__="/dash"` and reads `#iframe_token` | Upstream `base` default `/`; prefix support is runtime-only: Python rewrites `/assets/`, `/fonts/`, CSS `url()` and injects `__HERMES_BASE_PATH__` when `X-Forwarded-Prefix` is set (`web_server_dashboard.py@v2026.9.24:93-200`). `BrowserRouter basename={HERMES_BASE_PATH}` (`web/src/main.tsx`) | **PARTIAL** | Two ways to drop the second build: (a) proxy `/dash*` to `official-dashboard:9119` with `header_up X-Forwarded-Prefix /dash`; (b) keep static. (a) needs a decision: `/dash` documents become public proxy routes (the contract forbids bearer-injecting proxies, but a gated dashboard injects no token), and the `#iframe_token` bootstrap is lost, so the tokenless new-tab link `/dash/#iframe_token=` (shim `openAdminPanel`) would need the cookie handoff instead (`/_sidecar/dashboard-login`, which already exists). UNVERIFIED end to end | M |
| `/dash/api*` | strip `/dash`, to sidecar (cookie/bearer/header/query) | Dashboard APIs live at `/api`; sidecar also proxies `/api/pty`, `/api/events`, `/api/console` WS (`DASHBOARD_WS_PATHS`, `sidecar-script.ts:1398`) | **KEEP-AS-SEAM** (Hivra) | none | 0 |
| `@hermesDesktopDocument` (GET text/html outside `/dash /api ...`) | rewrite to webchat `index.html` | Not needed for HashRouter (0.5) | **KEEP** until probed | Removing it risks "Admin Panel replaced chat" regression if any non-hash document URL exists. Probe by loading `/sessions`, `/chat` on a canary box before removal | S |
| `/desktop*` | header/bearer/query token to sidecar; public `GET /desktop/api/status` to dashboard | n/a | see table 7 | | |
| `/dash/dashboard-plugins/*` | no-auth proxy to dashboard | `usePlugins.ts` builds `${HERMES_BASE_PATH}/dashboard-plugins/<name>/<entry>` | works as is | | 0 |

## 7. Native Desktop remote gateway (0.21.3 to 0.21.5)

What the releases say: v0.21.3 notes cover only gateway refresh-token coalescing for Portal OAuth ("remote-gateway sign-in fixes", `releases` v2026.9.14) plus a state.db handle leak fix. v0.21.4/0.21.5 notes are pointers to a deferred v0.22.0 changelog (UNVERIFIED details beyond code reading).
What the code does (`apps/desktop/electron/*@v2026.9.24`):
- `probeRemoteAuthMode(url)`: public `GET ${base}/api/status`; `auth_required:true` means mode `oauth`, else `token` (`main.ts:11066-11140`, `connection-config.ts:1050`). In oauth mode it also fetches `${base}/api/auth/providers`; if every provider `supports_password` the UI shows the gateway's `/login` password form (cookie + `POST /auth/password-login`), otherwise a gateway-brokered PKCE flow (`dashboard_auth/native_flow.py`). WS then uses a freshly minted single-use ticket (`POST /api/auth/ws-ticket`).
- token mode: header `X-Hermes-Session-Token`, `ws?token=`, URL path prefix kept (`normalizeRemoteBaseUrl` keeps `/desktop`).

| Question | Finding | Verdict | Blocks | Effort |
|---|---|---|---|---|
| Does it work against `https://<box>/desktop` with the single key? | Token mode: yes by design (Caddy matches header/bearer/query, `webui-instance-builder.ts:2113-2160`), reachable via env `HERMES_DESKTOP_REMOTE_URL`+`_TOKEN` which forces token mode (`desktop-remote-route.ts`). Settings UI path: `/desktop/api/status` is the one public path and goes straight to the gated dashboard with no rewrite, so `auth_required:true` is returned and the UI picks **oauth** (`gateway-settings.tsx:475-481`); the follow-ups `/desktop/api/auth/providers`, `/desktop/login`, `/desktop/auth/*` are 401 at Caddy (`@desktopUnauthed`). So UI sign-in with the key likely fails or shows a dead login. **UNVERIFIED live; code evidence only** | **PARTIAL / likely broken in UI** | Hivra Caddy exposes only `/desktop/api/status` publicly | M |
| Fix options | (a) sidecar/Caddy rewrite `/desktop/api/status` to `auth_required:false` (forces token mode, keeps today's single-key design); (b) route `/desktop*` auth endpoints to the dashboard with `X-Forwarded-Prefix: /desktop` so upstream's own password sign-in (username `hivra`, password = key) works and tickets replace `?token=`; (b) is upstream-native but cookies/Path/Secure and WS ticket forwarding are UNVERIFIED | decision for Ash | (a) is the smallest | S for (a) |
| Does it make fork `apps/desktop` changes unnecessary? | The fork touches no `electron/` file. Native users run upstream's official app. Nothing in the fork is a native-Desktop dependency, and nothing in native sign-in removes a fork change, because all fork renderer changes serve the browser build or Hivra product UX | **n/a** | | |

## 8. `hermes_cli/web_server.py` (~445 added lines) item by item

| Hunk (approx lines) | Needed by Hivra? | Verdict |
|---|---|---|
| `/webchat` Python mount (66) | No. Caddy serves the bundle statically; contract forbids proxying it; `HERMES_WEBCHAT_DIST` never set by Hivra builder | **REPLACE** (delete; keep `webchat_dist` bake for Caddy extraction) |
| `ModelAssignment`/`Moa*` pydantic classes (~100) | Upstream owns them in `hermes_cli/web_models.py@v2026.9.24:102-159` | **REPLACE** (drop on resync) |
| `/api/attachments/upload` + helpers (~130) | Shim only | **PARTIAL** (see 5; tied to shim change) |
| `_provider_profile_base_url` + adopt on provider switch (~30) | Surplus BYOK routing | KEEP-AS-SEAM (provider plugin concern) |
| `/api/status.dashboard_url` (3) | Onboarding Venice card | KEEP-AS-SEAM |
| `_fs_default_cwd` /workspace-first (17) | cwd | PARTIAL (use `TERMINAL_CWD`) |
| `_media_serve_roots` + `/workspace` (3) | chat media | KEEP-AS-SEAM |
| `/api/ops/backups` + backup dir root + query-token (~50) | maintenance UI | PARTIAL (use Admin Panel) |
| `_gateway_health_api_key` + route timeout (~45) | status accuracy | PARTIAL (verify) |
| `HERMES_DASHBOARD_TRUST_PROXY` (11) | never set | **REPLACE** (delete) |

## 9. Recommendation for this sprint

**Drop now (no behavior risk, mostly deletions):**
- `web/src/components/Backdrop.tsx` (dead), `apps/desktop/src/lib/gateway-ws-url.ts` (+ its test; upstream has the shared version), the Python `/webchat` mount, `ModelAssignment`/`Moa*` classes, the `HERMES_DASHBOARD_TRUST_PROXY` hunk, the shim's gold `installBrandSkin()` (after one visual check).
- Fix `webfree-contract.md` row 13 narrative (HashRouter, not history router). Keep the Caddy rule until probed.

**Drop after one cheap verification each:** About/updates patches (check `can_apply:false` in container path); gateway health-bearer hunk; backup UI + 3 py hunks; JS file-tree fallback once `TERMINAL_CWD=/workspace` is set.

**Keep as marked seams, smallest form:**
1. **`apps/desktop/src/lib/web-shim.ts` + `web-terminal.ts`**: already add-only new files; only change is `main.tsx` line 1 import. Keep. Reduce merge cost by (a) generating no-op stubs for every preload key so new upstream keys cannot throw (add a Proxy fallback returning an async no-op for unknown keys, optional chaining kept), (b) a CI test that diffs preload keys against shim keys and fails on non-optional uses.
2. **One add-only bundled plugin `apps/desktop/src/plugins/hivra/plugin.tsx`** (vite-glob auto-registered, so no core edits) holding: Hivra theme(s) via `THEMES_AREA`, Admin Panel `sidebar.nav` entry, appearance/send-message window listeners. Then revert `presets.ts`, `themes/context.tsx`, `sidebar/index.tsx`, `types.ts`, `wiring.tsx`, `use-session-actions` hunks. Unproven bits (UNVERIFIED): contributed theme as boot default, `sidebar.nav` row that opens an external tab rather than a route page, "submit text as user" from SDK. If any fails, keep that single hunk as a `hermes-fork:` patch.
3. **Core patches that cannot be add-only:** composer `context-menu.tsx` (user-activation in iframe), `use-composer-actions.ts` upload-then-attach, `use-gateway-boot.ts` transport-retry, onboarding Venice card, ModelPicker "authenticated" filter. Keep each marked `hermes-fork:` and listed in `.hermesos/customizations.yaml`.
4. **Dockerfile `webchat_build` stage + `--base=/webchat/`** stays (depends on `apps/desktop` building in a node image on every upstream sync; image does not install `apps/*` itself, `Dockerfile@v2026.9.24:419`). `/dash` second build + `inject-dash-bootstrap.cjs` stay this sprint; revisit option (a) in table 6 afterwards.
5. **`/api/attachments/upload`** stays until the shim is moved to `/api/files/upload` with `HERMES_DASHBOARD_FILES_ROOT=/workspace` (about a 30-line shim change plus env on official-dashboard); then delete ~130 py lines.

**Not replaceable by upstream:** the rich chat (iframe), the browser bridge, the browser terminal, the iframe file picker, Hivra product onboarding. **Replaceable by config/env, not fork code:** files root, default cwd, container update gating, Admin Panel backup.

**Do before trusting native Desktop for customers (needs a live read-only probe, not done here):** `curl https://<canary box>/desktop/api/status` and check `auth_required`; then try Desktop Settings > Gateway with the box URL. Likely outcome per code is the oauth branch (table 7).

## 10. UNVERIFIED list
- Live behavior of any box, Desktop sign-in UI against `/desktop`, rendered gold-vs-red skin conflict.
- Which of the ~20 non-optional missing bridge calls crash in the browser.
- Plugin SDK ability to set a boot-default theme, add an external-link nav row, or submit a prompt as a user.
- `/api/files/upload` size cap and body-limit behavior vs the fork's 50 MB; sidecar passing `POST /api/auth/ws-ticket`.
- v0.21.4/0.21.5 release notes are summary-only; no claims beyond code read at `v2026.9.24`. `upstream/main` (2026-10-07) was spot-checked for web `ChatPage`, `/api/terminal`, iframe commits only.
- The fork sits ~1.5 months behind (v0.20.5); `web_server.py` was split into `web_routers/*` + `web_server_*.py` upstream, so every remaining `web_server.py` hunk becomes a re-port, not a merge.
