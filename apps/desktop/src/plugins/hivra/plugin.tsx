/**
 * Hivra hosted-web integration, as one add-only bundled plugin.
 *
 * It replaces what used to be hunks in upstream-owned files: the Hivra theme
 * (themes/presets.ts), the dashboard appearance / starter-prompt listeners
 * (themes/context.tsx, contrib/wiring.tsx), the Admin Panel sidebar row
 * (app/types.ts, sidebar/index.tsx, use-session-actions) and phone polish.
 *
 * INERT outside the hosted web client: `window.__HERMES_WEB_CLIENT__` is set by
 * lib/web-shim.ts only when it installs the browser bridge, so a Desktop
 * (Electron) build that happens to bundle this file registers nothing.
 */

import './web.css'

import {
  Codicon,
  type HermesPlugin,
  host,
  type RouteContribution,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  type SidebarNavContribution,
  STATUSBAR_AREAS,
  THEMES_AREA,
  useTheme
} from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { useLocation } from 'react-router'

import { createDashboardBridge, type DashboardBridge, readDashboardModeFromUrl } from './dashboard-bridge'
import { HIVRA_SKIN_NAME, hivraTheme } from './themes'

const ADMIN_PANEL_PATH = '/admin-panel'
const PHONE_PANES = ['sessions', 'files', 'review'] as const

// Plugins may import only the SDK, so these mirror the app's own constants. They are pinned
// by src/contrib/hivra-plugin.test.tsx against the real exports (themes/context.tsx,
// components/pane-shell): if upstream renames one, that test fails instead of a silent no-op.
export const SKIN_STORAGE_KEY = 'hermes-desktop-theme-v2'
export const MODE_STORAGE_KEY = 'hermes-desktop-mode-v1'
export const PANE_REVEAL_EVENT = 'hermes:pane-toggle-reveal'

const readStored = (key: string): null | string => {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

const writeStored = (key: string, value: string) => {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    /* private mode: the app default applies */
  }
}

const isWebClient = () =>
  typeof window !== 'undefined' &&
  Boolean((window as unknown as { __HERMES_WEB_CLIENT__?: boolean }).__HERMES_WEB_CLIENT__)

interface AdminBridge {
  getAdminPanelUrl?: () => string
  openAdminPanel?: () => boolean
}

const adminBridge = (): AdminBridge =>
  typeof window === 'undefined' ? {} : ((window.hermesDesktop as AdminBridge) ?? {})

/**
 * First run paints the Hivra skin. `DEFAULT_SKIN_NAME` is upstream's constant,
 * so the default is seeded into the storage the theme provider reads at its
 * first render (plugins register at import time, before it mounts; the
 * contributed theme resolves reactively). Only when UNSET: an explicit pick
 * from Settings / Cmd+K is never overridden. Mode already defaults to `system`.
 */
export function seedDefaultSkin(): void {
  if (readStored(SKIN_STORAGE_KEY) === null) {
    writeStored(SKIN_STORAGE_KEY, HIVRA_SKIN_NAME)
  }
}

/** Dashboard `?theme=` first-paint hint (persisted like the live message is). */
export function seedDashboardMode(): void {
  const hint = readDashboardModeFromUrl()

  if (hint) {
    writeStored(MODE_STORAGE_KEY, hint)
  }
}

/** Phone: any navigation retires the pinned sidebar / files / review overlays. */
export function closeNarrowOverlays(): void {
  if (typeof window === 'undefined' || !host.state.viewport.get().narrow) {
    return
  }

  for (const id of PHONE_PANES) {
    window.dispatchEvent(new CustomEvent(PANE_REVEAL_EVENT, { detail: { id, mode: 'close' } }))
  }
}

function enablePhoneViewport(): void {
  window.document.documentElement.setAttribute('data-hermes-web-client', '')

  // viewport-fit=cover exposes env(safe-area-inset-*) on notched phones;
  // interactive-widget=resizes-content makes the layout viewport track the
  // on-screen keyboard. Pinch-zoom stays enabled on purpose.
  const meta = window.document.querySelector<HTMLMetaElement>('meta[name="viewport"]')
  const content = meta?.getAttribute('content') ?? ''

  if (meta && !content.includes('viewport-fit')) {
    meta.setAttribute('content', `${content}, viewport-fit=cover, interactive-widget=resizes-content`)
  }
}

let bridge: DashboardBridge | null = null

/** Mounted (renders nothing) so it can reach the router + theme provider. */
function HostBridge() {
  const { setMode } = useTheme()
  const { key } = useLocation()

  useEffect(() => {
    bridge?.attachModeSink(setMode)

    return () => bridge?.attachModeSink(null)
  }, [setMode])

  useEffect(closeNarrowOverlays, [key])

  return null
}

let lastAutoOpen = 0

/**
 * The sidebar row routes here (a `sidebar.nav` row can only navigate, it cannot
 * open an external tab). Opening from an effect keeps the one-click feel where
 * the browser still honours the click's activation (Chrome); where it does not
 * (Safari), the link below is the one tap that works.
 *
 * Only while the click that brought the user here is still "active": a reload or
 * a restored route must never pop a tab (or, in an embedded browser, navigate the
 * page away) by itself, so without live activation the link is the only door.
 */
export function AdminPanelPage() {
  const [blocked, setBlocked] = useState(false)

  useEffect(() => {
    // lastAutoOpen also absorbs React StrictMode's double-run in dev.
    if (Date.now() - lastAutoOpen < 2_000 || navigator.userActivation?.isActive === false) {
      return
    }

    lastAutoOpen = Date.now()
    setBlocked(adminBridge().openAdminPanel?.() === false)
  }, [])

  const href = adminBridge().getAdminPanelUrl?.() ?? '/dash/'

  return (
    <div className="grid h-full place-items-center p-6">
      <div className="flex max-w-sm flex-col items-center gap-3 text-center">
        <Codicon name="dashboard" size="1.5rem" />
        <h2 className="text-base font-semibold">Admin Panel</h2>
        <p className="text-sm text-muted-foreground">
          {blocked
            ? 'Your browser blocked the new tab. Open it with the link below.'
            : 'The Admin Panel opens in a new tab: telemetry, config, channels and logs.'}
        </p>
        <a
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground"
          href={href}
          rel="noopener noreferrer"
          target="_blank"
        >
          Open Admin Panel
        </a>
      </div>
    </div>
  )
}

const plugin: HermesPlugin = {
  id: 'hivra',
  name: 'Hivra',
  description: 'Hivra web client: brand theme, Admin Panel link, dashboard bridge, phone polish.',
  register(ctx) {
    if (!isWebClient()) {
      return
    }

    seedDefaultSkin()
    seedDashboardMode()
    enablePhoneViewport()

    bridge = createDashboardBridge({
      setTimeout: ctx.setTimeout,
      submit: text => host.composer.submit(null, text)
    })
    ctx.addEventListener(window, 'message', event => bridge?.onMessage(event as MessageEvent))
    ctx.onDispose(() => {
      bridge = null
    })

    ctx.registerMany([
      { id: 'theme-hivra', area: THEMES_AREA, data: hivraTheme },
      {
        id: 'admin-panel-page',
        area: ROUTES_AREA,
        data: { path: ADMIN_PANEL_PATH } satisfies RouteContribution,
        render: () => <AdminPanelPage />
      },
      {
        id: 'admin-panel-nav',
        area: SIDEBAR_NAV_AREA,
        order: 90,
        data: { codicon: 'dashboard', label: 'Admin Panel', path: ADMIN_PANEL_PATH } satisfies SidebarNavContribution
      },
      { id: 'host-bridge', area: STATUSBAR_AREAS.right, order: 999, render: () => <HostBridge /> }
    ])
  }
}

export default plugin
