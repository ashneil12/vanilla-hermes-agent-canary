#!/usr/bin/env node
/*
 * HermesOS — /dash static-bake bootstrap injector.
 *
 * The primary dashboard SPA is served at /desktop by the backend
 * (hermes_cli/web_server.py mount_spa), which injects window.__HERMES_BASE_PATH__
 * (from X-Forwarded-Prefix) and, in --insecure mode, window.__HERMES_SESSION_TOKEN__
 * server-side. That bundle is built with the default base=/ and is left untouched.
 *
 * The HermesOS "Admin Panel" nav item opens the SAME SPA at /dash, served as a
 * STATIC file_server by the control-plane Caddy (no backend HTML injection). So a
 * second bundle is baked with --base=/dash/ (assets resolve at /dash/assets/*),
 * and THIS script splices a tiny classic <script> into its <head> that supplies
 * the two globals the SPA reads at import time (src/lib/api.ts):
 *   - window.__HERMES_BASE_PATH__   → "/dash"  (BrowserRouter basename + every API/WS/SSE URL)
 *   - window.__HERMES_SESSION_TOKEN__ → the per-instance bearer, read from the
 *     dashboard handoff hash (#iframe_token=<token>, with #token= as a manual fallback)
 *
 * A classic inline <script> in <head> runs before the deferred type=module bundle,
 * so the globals are set before readBasePath()/getSessionToken() first run.
 *
 * Usage: node inject-dash-bootstrap.cjs <path-to-index.html>
 */
const fs = require("fs");

const file = process.argv[2];
if (!file) {
  console.error("inject-dash-bootstrap: missing <index.html> argument");
  process.exit(2);
}

const boot =
  '<script>(function(){try{' +
  'var m=(location.hash||"").match(/[#&](?:iframe_token|token)=([^&]+)/);' +
  'if(m&&m[1])window.__HERMES_SESSION_TOKEN__=decodeURIComponent(m[1]);' +
  '}catch(e){}' +
  'window.__HERMES_BASE_PATH__="/dash";' +
  "})();</script>";

let html = fs.readFileSync(file, "utf8");

// Idempotent: never inject twice (re-runs, layer cache).
if (html.includes('__HERMES_BASE_PATH__="/dash"')) {
  console.log("inject-dash-bootstrap: already present, skipping " + file);
  process.exit(0);
}

if (!html.includes("</head>")) {
  console.error("inject-dash-bootstrap: no </head> in " + file);
  process.exit(1);
}

html = html.replace("</head>", boot + "</head>");
fs.writeFileSync(file, html);
console.log("inject-dash-bootstrap: injected /dash bootstrap into " + file);
