#!/usr/bin/env node
/*
 * HermesOS — /dash static-bake bootstrap injector.
 *
 * The dashboard SPA is baked twice: the default base=/ build (hermes_cli/web_dist,
 * served at /desktop by the backend, which injects globals server-side) and a
 * base=/dash build (hermes_cli/web_dist_dash) for the "Admin Panel" nav item,
 * served as a STATIC file_server by the control-plane Caddy (no backend
 * injection). This script splices a tiny classic <head> script into the /dash
 * bundle's index.html that supplies the two globals src/lib/api.ts reads at
 * import time:
 *   - window.__HERMES_BASE_PATH__   = "/dash"  (BrowserRouter basename + API/WS/SSE URLs)
 *   - window.__HERMES_SESSION_TOKEN__ from the #iframe_token handoff hash (#token fallback)
 *
 * A classic inline <head> script runs before the deferred module bundle, so the
 * globals are set before readBasePath()/getSessionToken() first run.
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
