/**
 * Hosted-web shim for `window.hermesDesktop`.
 *
 * The desktop renderer normally gets all native capability through the
 * Electron preload bridge (`electron/preload.cjs`). When this same renderer
 * is built and served as a plain browser SPA (HermesOS "web rich-chat"),
 * there is no preload — so we install a browser-native implementation here.
 *
 * Design:
 *  - CHAT PATH is fully supported: `getConnection()` resolves the backend
 *    base URL + WS URL + bearer token from page origin + injected config, and
 *    `api()` is a `fetch` wrapper. The JSON-RPC gateway WebSocket and the REST
 *    session/config endpoints are all served by the same backend
 *    (`hermes_cli/web_server.py`), reachable through the edge Caddy `/desktop`
 *    route.
 *  - OS conveniences (notify, clipboard, open-external, image save, mic) map
 *    to standard browser APIs.
 *  - LOCAL-only features (terminal PTY, local FS browse/preview/watch, native
 *    file dialogs, auto-update, bootstrap installer) are benign stubs — the
 *    side panels that use them are not on the chat critical path.
 *
 * This module is a SIDE-EFFECT import: it installs the global only when no
 * Electron bridge is present, so importing it under Electron is a no-op.
 */

interface WebRuntimeConfig {
  /** API base path that the edge proxy maps to the dashboard backend. */
  apiBase: string
  /** Bearer token for the dashboard backend. */
  token: string
}

function resolveConfig(): WebRuntimeConfig {
  const w = window as unknown as {
    __HERMES_WEB_API_BASE__?: string
    __HERMES_WEB_TOKEN__?: string
    // Injected by the dashboard backend (hermes_cli/web_server.py) when this
    // bundle is served from the agent image, mirroring the dashboard SPA.
    __HERMES_SESSION_TOKEN__?: string
    __HERMES_BASE_PATH__?: string
  }

  // Token precedence: location.hash → injected global → stored.
  // Hash key: the HermesOS control-plane dashboard hands the per-instance
  // bearer off as `#iframe_token=<apiServerKey>` (the same handoff webui's
  // shim consumes — see hermesdeploy webui-handoff.ts). A direct/manual link
  // may use the plainer `#token=<bearer>`. Accept either; iframe_token wins.
  let token = ''
  try {
    const hash = window.location.hash.replace(/^#/, '')
    const params = new URLSearchParams(hash)
    const fromHash = params.get('iframe_token') || params.get('token')
    if (fromHash) {
      token = fromHash
      // Persist for reloads, then scrub the token out of the visible URL.
      try {
        sessionStorage.setItem('hermes_web_token', fromHash)
      } catch {
        /* ignore */
      }
      params.delete('iframe_token')
      params.delete('token')
      const rest = params.toString()
      const cleanHash = rest ? `#${rest}` : ''
      window.history.replaceState(null, '', window.location.pathname + window.location.search + cleanHash)
    }
  } catch {
    /* ignore */
  }
  // Image-served: the backend injects __HERMES_SESSION_TOKEN__ into index.html.
  if (!token && typeof w.__HERMES_SESSION_TOKEN__ === 'string' && w.__HERMES_SESSION_TOKEN__) {
    token = w.__HERMES_SESSION_TOKEN__
  }
  if (!token && typeof w.__HERMES_WEB_TOKEN__ === 'string') {
    token = w.__HERMES_WEB_TOKEN__
  }
  if (!token) {
    try {
      token = sessionStorage.getItem('hermes_web_token') ?? ''
    } catch {
      /* ignore */
    }
  }

  // API base precedence: __HERMES_BASE_PATH__ (injected by the backend when
  // image-served — may legitimately be "" for root, so test by type) →
  // __HERMES_WEB_API_BASE__ (hand-deploy override) → "/desktop" default.
  let apiBase: string
  if (typeof w.__HERMES_BASE_PATH__ === 'string') {
    apiBase = w.__HERMES_BASE_PATH__
  } else if (typeof w.__HERMES_WEB_API_BASE__ === 'string') {
    apiBase = w.__HERMES_WEB_API_BASE__
  } else {
    apiBase = '/desktop'
  }
  apiBase = apiBase.replace(/\/$/, '')

  return { apiBase, token }
}

function buildUrls(config: WebRuntimeConfig): { baseUrl: string; wsUrl: string } {
  const origin = window.location.origin
  const baseUrl = `${origin}${config.apiBase}`
  const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsBase = `${wsProto}//${window.location.host}${config.apiBase}`
  const qs = config.token ? `?token=${encodeURIComponent(config.token)}` : ''
  const wsUrl = `${wsBase}/api/ws${qs}`
  return { baseUrl, wsUrl }
}

async function fetchJson<T>(request: { path: string; method?: string; body?: unknown; timeoutMs?: number }): Promise<T> {
  const config = resolveConfig()
  const { baseUrl } = buildUrls(config)
  const controller = new AbortController()
  const timeout = request.timeoutMs && request.timeoutMs > 0 ? request.timeoutMs : 30_000
  const timer = window.setTimeout(() => controller.abort(), timeout)
  try {
    const headers: Record<string, string> = {}
    if (config.token) {
      headers.Authorization = `Bearer ${config.token}`
    }
    let body: BodyInit | undefined
    if (request.body !== undefined && request.body !== null) {
      headers['Content-Type'] = 'application/json'
      body = JSON.stringify(request.body)
    }
    const res = await fetch(`${baseUrl}${request.path}`, {
      method: request.method ?? (request.body !== undefined ? 'POST' : 'GET'),
      headers,
      body,
      signal: controller.signal,
      credentials: 'omit'
    })
    const text = await res.text()
    const data = text ? JSON.parse(text) : undefined
    if (!res.ok) {
      const message =
        (data && typeof data === 'object' && 'error' in data && (data as { error?: string }).error) ||
        `HTTP ${res.status} for ${request.path}`
      throw new Error(String(message))
    }
    return data as T
  } finally {
    window.clearTimeout(timer)
  }
}

function noopUnsubscribe(): () => void {
  return () => {}
}

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

function installWebShim(): void {
  const config = resolveConfig()

  const bridge = {
    getConnection: async () => {
      const fresh = resolveConfig()
      const { baseUrl, wsUrl } = buildUrls(fresh)
      return {
        baseUrl,
        wsUrl,
        token: fresh.token,
        mode: 'remote' as const,
        source: 'env' as const,
        isFullscreen: false,
        nativeOverlayWidth: 0,
        windowButtonPosition: null,
        logs: [] as string[]
      }
    },

    getBootProgress: async () => ({
      error: null,
      fakeMode: false,
      message: 'ready',
      phase: 'ready',
      progress: 100,
      running: false,
      timestamp: Date.now()
    }),

    getConnectionConfig: async () => ({
      envOverride: true,
      mode: 'remote' as const,
      remoteTokenPreview: null,
      remoteTokenSet: Boolean(config.token),
      remoteUrl: `${window.location.origin}${config.apiBase}`
    }),
    saveConnectionConfig: async (p: unknown) => ({
      envOverride: true,
      mode: 'remote' as const,
      remoteTokenPreview: null,
      remoteTokenSet: Boolean(config.token),
      remoteUrl: `${window.location.origin}${config.apiBase}`,
      ...(p as object)
    }),
    applyConnectionConfig: async (p: unknown) => bridge.saveConnectionConfig(p),
    testConnectionConfig: async () => {
      try {
        const status = await fetchJson<{ version?: string }>({ path: '/api/status' })
        return { baseUrl: `${window.location.origin}${config.apiBase}`, ok: true, version: status?.version ?? null }
      } catch {
        return { baseUrl: `${window.location.origin}${config.apiBase}`, ok: false, version: null }
      }
    },

    api: fetchJson,

    notify: async (payload: { title?: string; body?: string; silent?: boolean }) => {
      try {
        if (typeof Notification === 'undefined') return false
        if (Notification.permission === 'granted') {
          new Notification(payload.title ?? 'Hermes', { body: payload.body, silent: payload.silent })
          return true
        }
        if (Notification.permission !== 'denied') {
          const perm = await Notification.requestPermission()
          if (perm === 'granted') {
            new Notification(payload.title ?? 'Hermes', { body: payload.body, silent: payload.silent })
            return true
          }
        }
      } catch {
        /* ignore */
      }
      return false
    },

    requestMicrophoneAccess: async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        stream.getTracks().forEach(t => t.stop())
        return true
      } catch {
        return false
      }
    },

    // Local-filesystem reads are not available in the browser. Resolve to
    // empty/benign values so the (non-chat) preview/files panels degrade
    // gracefully rather than crash.
    readFileDataUrl: async () => '',
    readFileText: async (filePath: string) => ({ path: filePath, text: '', binary: false }),
    selectPaths: async () => [],
    readDir: async () => ({ entries: [] }),
    gitRoot: async () => null,
    normalizePreviewTarget: async () => null,
    watchPreviewFile: async (url: string) => ({ id: 'web-noop', path: url }),
    stopPreviewFileWatch: async () => true,

    writeClipboard: async (text: string) => {
      try {
        await navigator.clipboard.writeText(text)
        return true
      } catch {
        return false
      }
    },

    saveImageFromUrl: async (url: string) => {
      try {
        const res = await fetch(url)
        const blob = await res.blob()
        const name = url.split('/').pop()?.split('?')[0] || 'image.png'
        triggerDownload(blob, name)
        return true
      } catch {
        return false
      }
    },
    saveImageBuffer: async (data: ArrayBuffer | Uint8Array, ext: string) => {
      const blob = new Blob([data as BlobPart], { type: `image/${ext.replace(/^\./, '')}` })
      triggerDownload(blob, `image.${ext.replace(/^\./, '')}`)
      return 'download'
    },
    saveClipboardImage: async () => '',
    getPathForFile: () => '',

    setTitleBarTheme: () => {},
    setPreviewShortcutActive: () => {},

    openExternal: async (url: string) => {
      window.open(url, '_blank', 'noopener,noreferrer')
    },
    fetchLinkTitle: async (url: string) => url,

    // HermesOS "Admin Panel" sidebar item → opens the full dashboard
    // (telemetry / config / channels / TUI chat) at /dash, carrying the
    // session token in the URL fragment so it authenticates without a
    // second login. Web-only; the native desktop app has no /dash route.
    openAdminPanel: () => {
      const t = resolveConfig().token
      const url = t ? `/dash/#iframe_token=${encodeURIComponent(t)}` : '/dash/'
      window.open(url, '_blank', 'noopener,noreferrer')
    },

    settings: {
      getDefaultProjectDir: async () => ({ defaultLabel: 'Workspace', dir: null }),
      pickDefaultProjectDir: async () => ({ canceled: true, dir: null }),
      setDefaultProjectDir: async (dir: null | string) => ({ dir })
    },

    revealLogs: async () => ({ ok: false, path: '', error: 'unavailable on web' }),
    getRecentLogs: async () => ({ path: '', lines: [] as string[] }),

    // Terminal side panel: no PTY in the browser.
    terminal: {
      start: async () => {
        throw new Error('Terminal is not available in the web client')
      },
      write: async () => false,
      resize: async () => false,
      dispose: async () => true,
      onData: () => noopUnsubscribe(),
      onExit: () => noopUnsubscribe()
    },

    onClosePreviewRequested: () => noopUnsubscribe(),
    onOpenUpdatesRequested: () => noopUnsubscribe(),
    onWindowStateChanged: () => noopUnsubscribe(),
    onPreviewFileChanged: () => noopUnsubscribe(),
    onBackendExit: () => noopUnsubscribe(),
    onBootProgress: () => noopUnsubscribe(),

    getBootstrapState: async () => ({
      active: false,
      manifest: null,
      stages: {},
      error: null,
      log: [] as Array<{ ts: number; stage: string | null; line: string }>,
      startedAt: null,
      completedAt: null,
      unsupportedPlatform: null
    }),
    resetBootstrap: async () => ({ ok: true }),
    repairBootstrap: async () => ({ ok: true }),
    cancelBootstrap: async () => ({ ok: true, cancelled: false }),
    onBootstrapEvent: () => noopUnsubscribe(),

    getVersion: async () => ({
      appVersion: 'web',
      electronVersion: '',
      nodeVersion: '',
      platform: 'web',
      hermesRoot: ''
    }),

    updates: {
      check: async () => ({ supported: false, reason: 'web client', message: 'Updates managed server-side' }),
      apply: async () => ({ ok: false, error: 'Updates managed server-side' }),
      getBranch: async () => ({ branch: 'web' }),
      setBranch: async (name: string) => ({ branch: name }),
      onProgress: () => noopUnsubscribe()
    }
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(window as any).hermesDesktop = bridge
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(window as any).__HERMES_WEB_CLIENT__ = true
}

// NOTE: the HermesOS dashboard launcher used to be a floating bottom-right
// button injected here. It now lives as the "Admin Panel" item in the left
// sidebar nav (see app/chat/sidebar + bridge.openAdminPanel above), so the
// floating button was removed.

/**
 * HermesOS brand skin (web-only). Re-tints the upstream blue accent
 * (--theme-primary / --theme-midground = #0053fd) to HermesOS gold/bronze
 * via a high-specificity stylesheet override — additive, so it never
 * conflicts with upstream's styles.css on a sync. Per-mode shades keep it
 * readable: a deeper gold on light, a brighter gold on dark. The native
 * desktop app never loads this (it has no web-shim), so it keeps upstream's
 * default theme; only the hosted HermesOS web surface is skinned.
 */
function installBrandSkin(): void {
  const inject = () => {
    if (document.getElementById('hermesos-skin')) return
    const style = document.createElement('style')
    style.id = 'hermesos-skin'
    style.textContent = [
      ':root{',
      '--theme-primary:#A67C1A!important;--theme-midground:#A67C1A!important;',
      '--ui-accent:#A67C1A!important;--ui-accent-secondary:#8A6914!important;--ui-blue:#A67C1A!important;',
      '--theme-warm:#CD7F32!important;}',
      ':root.dark{',
      '--theme-primary:#E0A82E!important;--theme-midground:#E0A82E!important;',
      '--ui-accent:#E0A82E!important;--ui-accent-secondary:#C8961E!important;--ui-blue:#E0A82E!important;',
      '--theme-warm:#CD7F32!important;}'
    ].join('')
    document.head.appendChild(style)
  }
  if (document.head) inject()
  else document.addEventListener('DOMContentLoaded', inject, { once: true })
}

/**
 * HermesOS — make dark mode "just work" on the hosted web surface.
 *
 * The desktop theme system (src/themes/context.tsx) defaults the color mode to
 * 'light' when nothing is stored. On the web we instead seed the *first-run*
 * default to 'system', so the rich chat follows the visitor's OS light/dark
 * preference automatically. The gold skin already ships a `:root.dark` variant
 * (installBrandSkin above: warm #E0A82E in dark vs #A67C1A in light), so dark
 * mode is correctly re-tinted with zero extra work.
 *
 * Only set when UNSET — this never overrides an explicit choice from the in-app
 * toggle (Cmd+K -> Light/Dark/System, or Settings -> Appearance), which persists
 * under the same key. KEEP IN SYNC with MODE_KEY in src/themes/context.tsx.
 */
const HERMES_MODE_KEY = 'hermes-desktop-mode-v1'
function seedDefaultColorMode(): void {
  try {
    if (!window.localStorage.getItem(HERMES_MODE_KEY)) {
      window.localStorage.setItem(HERMES_MODE_KEY, 'system')
    }
  } catch {
    /* localStorage unavailable (private mode) — fall back to the app default */
  }
}

if (typeof window !== 'undefined' && !(window as unknown as { hermesDesktop?: unknown }).hermesDesktop) {
  seedDefaultColorMode()
  installWebShim()
  installBrandSkin()
}

export {}

