/**
 * Dashboard <-> chat bridge for the hosted web client.
 *
 * The Hivra dashboard embeds this renderer in a cross-origin iframe and talks to
 * it with two postMessage types (guards mirror the originals: only when actually
 * framed, only from `window.parent`, only `source: 'hermes-dashboard'`):
 *
 *   hermes-dashboard:appearance    { appearance: { colorScheme } } -> light/dark sync
 *   hermes-dashboard:send-message  { text }                        -> send as the user
 *
 * Plain TS on purpose: it registers at plugin load, BEFORE React mounts, so an
 * early message from the dashboard is never missed. The live theme mode setter
 * only exists once the shell is mounted, so appearance messages that arrive
 * earlier are parked in `pendingMode` and applied by `attachModeSink`.
 */

export type DashboardColorScheme = 'dark' | 'light'

export const DASHBOARD_APPEARANCE_MESSAGE_TYPE = 'hermes-dashboard:appearance'
export const DASHBOARD_SEND_MESSAGE_TYPE = 'hermes-dashboard:send-message'
export const DASHBOARD_MESSAGE_SOURCE = 'hermes-dashboard'

// The composer may not be mounted yet when the dashboard fires a starter prompt.
const SUBMIT_RETRY_MS = 400
const SUBMIT_RETRY_LIMIT = 25

/** Mode hint the dashboard pre-encodes on the iframe URL (`?theme=`), when framed. */
export function readDashboardModeFromUrl(win: Window = window): DashboardColorScheme | null {
  if (win === win.parent) {
    return null
  }

  const theme = new URLSearchParams(win.location.search).get('theme')

  if (theme === 'dark') {
    return 'dark'
  }

  return theme === 'hermesos-light' || theme === 'light' ? 'light' : null
}

export interface DashboardBridgeDeps {
  /** Send `text` as if the user typed it; false when no composer claimed it. */
  submit: (text: string) => boolean
  /** Scoped timer (cleared when the plugin unloads). */
  setTimeout: (fn: () => void, ms: number) => () => void
  win?: Window
}

export interface DashboardBridge {
  /** Hand over the live mode setter once the theme provider is mounted. */
  attachModeSink: (apply: ((mode: DashboardColorScheme) => void) | null) => void
  /** The window `message` listener; exported for tests. */
  onMessage: (event: MessageEvent) => void
}

export function createDashboardBridge({ submit, setTimeout, win = window }: DashboardBridgeDeps): DashboardBridge {
  let sink: ((mode: DashboardColorScheme) => void) | null = null
  let pendingMode: DashboardColorScheme | null = null

  const submitWithRetry = (text: string, attempt = 0) => {
    if (submit(text) || attempt >= SUBMIT_RETRY_LIMIT) {
      return
    }

    setTimeout(() => submitWithRetry(text, attempt + 1), SUBMIT_RETRY_MS)
  }

  return {
    attachModeSink(apply) {
      sink = apply

      if (apply && pendingMode) {
        const mode = pendingMode

        pendingMode = null
        apply(mode)
      }
    },
    onMessage(event) {
      if (win === win.parent || event.source !== win.parent) {
        return
      }

      const data = event.data as {
        appearance?: { colorScheme?: unknown }
        source?: unknown
        text?: unknown
        type?: unknown
      } | null

      if (!data || typeof data !== 'object' || data.source !== DASHBOARD_MESSAGE_SOURCE) {
        return
      }

      if (data.type === DASHBOARD_APPEARANCE_MESSAGE_TYPE) {
        const scheme = data.appearance?.colorScheme

        if (scheme === 'dark' || scheme === 'light') {
          if (sink) {
            sink(scheme)
          } else {
            pendingMode = scheme
          }
        }

        return
      }

      if (data.type === DASHBOARD_SEND_MESSAGE_TYPE && typeof data.text === 'string') {
        const text = data.text.trim()

        if (text) {
          submitWithRetry(text)
        }
      }
    }
  }
}
