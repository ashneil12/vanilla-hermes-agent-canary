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
 *  - Terminal PTYs use the authenticated, session-scoped hosted sidecar when
 *    available. An older/unsupported server reports a capability error.
 *  - ATTACHMENTS: browser Files get a synthetic path (`web-files.ts`) and Desktop's
 *    own remote attach flow ships their bytes over the gateway WS at send time.
 *  - Bridge keys this shim does NOT define stay `undefined` ON PURPOSE: the
 *    renderer feature-detects Electron-only UI (`window.hermesDesktop?.cloud`,
 *    `typeof ...openWindow === 'function'`), so a catch-all no-op Proxy would
 *    switch those surfaces ON. `web-shim-drift.test.ts` guards against upstream
 *    adding a required key this shim neither implements nor has reviewed.
 *  - LOCAL-only features (local FS browse/preview/watch, native
 *    file dialogs, auto-update, bootstrap installer) are benign stubs — the
 *    side panels that use them are not on the chat critical path.
 *
 * This module is a SIDE-EFFECT import: it installs the global only when no
 * Electron bridge is present, so importing it under Electron is a no-op.
 */

import { getApiRequestConnection, getApiRequestProfile } from '../api/client'

import { imageMimeForExtension, readWebFileDataUrl, registerWebFile, selectBrowserFiles } from './web-files'
import { createWebTerminal } from './web-terminal'

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

async function fetchJson<T>(
  request: { path: string; method?: string; body?: unknown; timeoutMs?: number; keepalive?: boolean },
  config = resolveConfig()
): Promise<T> {
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

    const terminalRequest = request.path === '/api/desktop-terminal'

    const res = await fetch(`${baseUrl}${request.path}`, {
      method: request.method ?? (request.body !== undefined ? 'POST' : 'GET'),
      headers,
      body,
      signal: controller.signal,
      credentials: 'omit',
      // A redirect must not forward session credentials or typed shell input
      // to a different endpoint, even when fetch strips the bearer header.
      ...(terminalRequest ? { redirect: 'error' as const } : {}),
      ...(request.keepalive ? { keepalive: true } : {})
    })

    const text = await res.text()
    let data: unknown

    try {
      data = text ? JSON.parse(text) : undefined
    } catch (error) {
      if (terminalRequest) {
        if ([404, 405, 501].includes(res.status)) {
          throw new Error('This server does not support browser terminals')
        }

        throw new Error(
          `Terminal service returned a non-JSON response (HTTP ${res.status}); browser terminals may not be supported on this server`
        )
      }

      throw error
    }

    if (!res.ok) {
      const message =
        (data && typeof data === 'object' && 'error' in data && (data as { error?: string }).error) ||
        (terminalRequest && [404, 405, 501].includes(res.status)
          ? 'This server does not support browser terminals'
          : `HTTP ${res.status} for ${request.path}`)

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

function adminPanelUrl(): string {
  const t = resolveConfig().token

  return t ? `/dash/#iframe_token=${encodeURIComponent(t)}` : '/dash/'
}

function installWebShim(): void {
  const config = resolveConfig()

  const bridge = {
    getConnection: async (profile?: null | string) => {
      const fresh = resolveConfig()
      const { baseUrl, wsUrl } = buildUrls(fresh)
      const requestedProfile = (profile ?? '').trim()

      return {
        baseUrl,
        wsUrl,
        token: fresh.token,
        mode: 'remote' as const,
        source: 'env' as const,
        // Hosted HermesOS exposes one multi-profile gateway. Mark named
        // profile lookups as shared-primary so the renderer scopes RPCs with
        // `profile` on the existing socket instead of dialing the same URL as
        // a phantom secondary. The latter detaches the live runtime whenever
        // its 20-second hydration attempt closes (#hosted-profile-loop).
        ...(requestedProfile ? { profile: requestedProfile, sharedPrimary: true } : {}),
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
        if (typeof Notification === 'undefined') {
          return false
        }

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

    // Local-filesystem reads are not available in the browser. Picked / dropped
    // / pasted browser Files live behind synthetic paths (see web-files.ts);
    // Desktop's remote attach flow reads their bytes back through these two.
    readFileDataUrl: readWebFileDataUrl,
    readFileDataUrlForAttach: readWebFileDataUrl,
    readFileText: async (filePath: string) => ({ path: filePath, text: '', binary: false }),
    selectPaths: selectBrowserFiles,
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
    // Required bridge key (terminal "Paste" in the app context menu calls it
    // without a feature check). Denied permission / no clipboard API -> ''.
    readClipboard: async () => {
      try {
        return (await navigator.clipboard.readText()) ?? ''
      } catch {
        return ''
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
    // Pasted / dropped images: no disk to save to, so register the bytes under
    // a synthetic path; `image.attach_bytes` ships them at send time.
    saveImageBuffer: async (data: ArrayBuffer | Uint8Array, ext: string, name?: string) => {
      const cleanExt = ext.replace(/^\./, '') || 'png'
      const blob = new Blob([data as BlobPart], { type: imageMimeForExtension(cleanExt) })

      return registerWebFile(blob, name || `image.${cleanExt}`)
    },
    saveClipboardImage: async () => '',
    // Drag-drop / hidden-input Files: a synthetic path (the composer chip shows
    // its basename), resolved back to bytes by readFileDataUrl* above.
    getPathForFile: (file: File) => registerWebFile(file),

    setTitleBarTheme: () => {},
    setPreviewShortcutActive: () => {},

    openExternal: async (url: string) => {
      window.open(url, '_blank', 'noopener,noreferrer')
    },
    fetchLinkTitle: async (url: string) => url,

    // HermesOS "Admin Panel" (sidebar row from plugins/hivra) → the full
    // dashboard (telemetry / config / channels / TUI chat) at /dash, carrying
    // the session token in the URL fragment so it authenticates without a
    // second login. Web-only; the native desktop app has no /dash route.
    getAdminPanelUrl: adminPanelUrl,
    openAdminPanel: () => Boolean(window.open(adminPanelUrl(), '_blank', 'noopener,noreferrer')),

    // Required `profile` namespace. `switchProfile` calls `profile.set` without
    // a feature check; hosted web has ONE multi-profile gateway (profiles ride
    // `getConnection(profile)` -> sharedPrimary), so nothing relaunches here.
    // Only set/remember are defined: `getDefault` / `setDefault` stay absent so
    // the "default profile" affordances (feature-detected) stay hidden.
    profile: {
      remember: async (name: null | string) => ({ profile: name ?? 'default' }),
      set: async (name: null | string) => ({ profile: name ?? 'default' })
    },

    settings: {
      getDefaultProjectDir: async () => ({ defaultLabel: 'Workspace', dir: null }),
      pickDefaultProjectDir: async () => ({ canceled: true, dir: null }),
      setDefaultProjectDir: async (dir: null | string) => ({ dir })
    },

    revealLogs: async () => ({ ok: false, path: '', error: 'unavailable on web' }),
    getRecentLogs: async () => ({ path: '', lines: [] as string[] }),

    terminal: createWebTerminal({
      captureRequest: () => {
        const terminalConfig = resolveConfig()
        const { baseUrl } = buildUrls(terminalConfig)

        if (
          (terminalConfig.apiBase && !terminalConfig.apiBase.startsWith('/')) ||
          new URL(baseUrl).origin !== window.location.origin
        ) {
          throw new Error('Browser terminal requests must stay on this server')
        }

        return request => fetchJson(request, terminalConfig)
      },
      getProfile: getApiRequestProfile,
      getConnectionId: getApiRequestConnection
    }),

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

  ;(window as any).hermesDesktop = bridge

  ;(window as any).__HERMES_WEB_CLIENT__ = true
}

if (typeof window !== 'undefined' && !(window as unknown as { hermesDesktop?: unknown }).hermesDesktop) {
  installWebShim()
}

export {}
