import { host } from '@hermes/plugin-sdk'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { PANE_TOGGLE_REVEAL_EVENT } from '@/components/pane-shell'
import { modePref, skinPref, ThemeProvider, useTheme } from '@/themes/context'
import { listAllThemes, resolveTheme } from '@/themes/user-themes'

import {
  createDashboardBridge,
  DASHBOARD_APPEARANCE_MESSAGE_TYPE,
  DASHBOARD_SEND_MESSAGE_TYPE,
  readDashboardModeFromUrl
} from '../plugins/hivra/dashboard-bridge'
import plugin, {
  AdminPanelPage,
  closeNarrowOverlays,
  MODE_STORAGE_KEY,
  PANE_REVEAL_EVENT,
  seedDefaultSkin,
  SKIN_STORAGE_KEY
} from '../plugins/hivra/plugin'
import { HIVRA_SKIN_NAME } from '../plugins/hivra/themes'

import { createPluginContext } from './plugin'
import { registry } from './registry'

const setWebClient = (on: boolean) => {
  if (on) {
    ;(window as unknown as { __HERMES_WEB_CLIENT__?: boolean }).__HERMES_WEB_CLIENT__ = true
  } else {
    delete (window as unknown as { __HERMES_WEB_CLIENT__?: boolean }).__HERMES_WEB_CLIENT__
  }
}

function load() {
  const disposers: Array<() => void> = []

  plugin.register(createPluginContext('hivra', dispose => disposers.push(dispose)))

  return () => disposers.splice(0).forEach(dispose => dispose())
}

beforeEach(() => {
  window.localStorage.clear()
  window.document.documentElement.removeAttribute('data-hermes-web-client')
})

afterEach(() => {
  setWebClient(false)
  vi.restoreAllMocks()
})

describe('hivra plugin', () => {
  it('is inert outside the hosted web client (a Desktop build that bundles it registers nothing)', () => {
    const unload = load()

    expect(registry.getArea('themes').some(c => c.source === 'plugin:hivra')).toBe(false)
    expect(registry.getArea('sidebar.nav').some(c => c.source === 'plugin:hivra')).toBe(false)
    expect(skinPref.stored('default')).toBeNull()
    expect(window.document.documentElement.hasAttribute('data-hermes-web-client')).toBe(false)
    unload()
  })

  it('contributes the Hivra themes, the Admin Panel route + nav row and the host bridge', () => {
    setWebClient(true)
    const unload = load()
    const mine = (area: string) => registry.getArea(area).filter(c => c.source === 'plugin:hivra')

    expect(mine('themes').map(c => (c.data as { name: string }).name)).toEqual(['hivra'])
    expect(resolveTheme('hivra')?.darkColors?.primary).toBe('#ff3a3b')
    expect(listAllThemes().map(t => t.name)).toEqual(expect.arrayContaining(['hivra', 'nous']))
    expect(mine('routes').map(c => c.data)).toEqual([{ path: '/admin-panel' }])
    expect(mine('sidebar.nav').map(c => c.data)).toEqual([
      { codicon: 'dashboard', label: 'Admin Panel', path: '/admin-panel' }
    ])
    expect(mine('statusBar.right')).toHaveLength(1)
    expect(window.document.documentElement.hasAttribute('data-hermes-web-client')).toBe(true)

    unload()
    expect(registry.getArea('themes').some(c => c.source === 'plugin:hivra')).toBe(false)
    expect(resolveTheme('hivra')).toBeUndefined()
  })

  it('makes Hivra the first-run skin through the SAME storage the theme provider reads', () => {
    setWebClient(true)
    const unload = load()

    // skinPref is the theme provider's own accessor: if upstream renames the
    // storage key this fails instead of silently painting the default skin.
    expect(skinPref.resolve('default')).toBe(HIVRA_SKIN_NAME)
    unload()
  })

  it('the real ThemeProvider paints Hivra on its FIRST render, with light and dark palettes', () => {
    setWebClient(true)
    const unload = load()

    function Probe() {
      const { renderedMode, theme, themeName } = useTheme()

      return <output data-testid="probe">{`${themeName}|${theme.name}|${renderedMode}`}</output>
    }

    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>
    )

    // Plugins register at import time, so the contributed skin already resolves
    // when the provider reads its persisted pick: no flash of the default skin.
    expect(screen.getByTestId('probe').textContent).toMatch(/^hivra\|hivra-(light|dark)\|(light|dark)$/)
    expect(window.document.documentElement.style.getPropertyValue('--theme-primary')).toMatch(/#ff(2c2d|3a3b)/i)
    unload()
    cleanup()
  })

  it('never overrides an explicit skin pick', () => {
    skinPref.assign('default', 'mono')
    seedDefaultSkin()

    expect(skinPref.stored('default')).toBe('mono')
  })

  it("leaves the color mode on upstream's system default", () => {
    setWebClient(true)
    const unload = load()

    expect(modePref.resolve('default')).toBe('system')
    unload()
  })

  it('adds viewport-fit=cover to the viewport meta exactly once', () => {
    const meta = window.document.createElement('meta')

    meta.name = 'viewport'
    meta.content = 'width=device-width, initial-scale=1.0'
    window.document.head.appendChild(meta)
    setWebClient(true)

    const unload = load()
    const once = meta.content

    expect(once).toContain('viewport-fit=cover')
    expect(once).toContain('interactive-widget=resizes-content')
    unload()
    load()()
    expect(meta.content).toBe(once)
    meta.remove()
  })

  it('closeNarrowOverlays retires the pinned panes on a phone and does nothing on a wide viewport', () => {
    const seen = vi.fn((event: Event) => (event as CustomEvent).detail)
    const viewport = vi.spyOn(host.state.viewport, 'get')

    window.addEventListener(PANE_TOGGLE_REVEAL_EVENT, seen)
    viewport.mockReturnValue({ height: 800, narrow: false, width: 1200 } as never)
    closeNarrowOverlays()
    expect(seen).not.toHaveBeenCalled()

    viewport.mockReturnValue({ height: 800, narrow: true, width: 390 } as never)
    closeNarrowOverlays()
    window.removeEventListener(PANE_TOGGLE_REVEAL_EVENT, seen)

    expect(seen.mock.results.map(result => result.value)).toEqual([
      { id: 'sessions', mode: 'close' },
      { id: 'files', mode: 'close' },
      { id: 'review', mode: 'close' }
    ])
  })

  it('mirrors the app constants the plugin cannot import (a rename upstream fails here, not silently)', () => {
    expect(PANE_REVEAL_EVENT).toBe(PANE_TOGGLE_REVEAL_EVENT)

    window.localStorage.setItem(SKIN_STORAGE_KEY, 'mono')
    window.localStorage.setItem(MODE_STORAGE_KEY, 'dark')

    expect(skinPref.stored('default')).toBe('mono')
    expect(modePref.stored('default')).toBe('dark')
  })
})

describe('Admin Panel page', () => {
  const setActivation = (isActive: boolean | undefined) =>
    Object.defineProperty(navigator, 'userActivation', {
      configurable: true,
      value: isActive === undefined ? undefined : { isActive }
    })

  const bridge = (open: () => boolean) => {
    ;(window as unknown as { hermesDesktop: unknown }).hermesDesktop = {
      getAdminPanelUrl: () => '/dash/#iframe_token=t',
      openAdminPanel: open
    }
  }

  afterEach(() => {
    cleanup()
    setActivation(undefined)
    delete (window as unknown as { hermesDesktop?: unknown }).hermesDesktop
  })

  it('opens the panel in a new tab from the click that routed here, and keeps a link as the fallback', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(Date.now() + 60_000) // outside the auto-open debounce window
    setActivation(true)
    const open = vi.fn(() => true)

    bridge(open)
    render(<AdminPanelPage />)

    expect(open).toHaveBeenCalledOnce()
    expect(screen.getByRole('link', { name: 'Open Admin Panel' }).getAttribute('href')).toBe('/dash/#iframe_token=t')
    vi.useRealTimers()
  })

  it('says so when the browser blocked the tab', () => {
    vi.useFakeTimers()
    vi.setSystemTime(Date.now() + 120_000)
    setActivation(true)
    bridge(() => false)
    render(<AdminPanelPage />)

    expect(screen.getByText(/blocked the new tab/i)).toBeTruthy()
    vi.useRealTimers()
  })

  it('never auto-opens on a reload / restored route (no live user activation)', () => {
    vi.useFakeTimers()
    vi.setSystemTime(Date.now() + 180_000)
    setActivation(false)
    const open = vi.fn(() => true)

    bridge(open)
    render(<AdminPanelPage />)

    expect(open).not.toHaveBeenCalled()
    expect(screen.getByRole('link', { name: 'Open Admin Panel' })).toBeTruthy()
    vi.useRealTimers()
  })
})

describe('dashboard bridge', () => {
  const parent = {} as Window

  const framed = (): Window => ({ parent, location: { search: '' } }) as unknown as Window

  const appearance = (colorScheme: unknown, source: unknown = parent, from = 'hermes-dashboard') =>
    ({
      data: { appearance: { colorScheme }, source: from, type: DASHBOARD_APPEARANCE_MESSAGE_TYPE },
      source
    }) as MessageEvent

  const send = (text: unknown, source: unknown = parent, from = 'hermes-dashboard') =>
    ({ data: { source: from, text, type: DASHBOARD_SEND_MESSAGE_TYPE }, source }) as MessageEvent

  const make = (submit = vi.fn(() => true)) => {
    const timers: Array<() => void> = []

    const bridge = createDashboardBridge({
      setTimeout: fn => {
        timers.push(fn)

        return () => {}
      },
      submit,
      win: framed()
    })

    return { bridge, submit, timers }
  }

  it('applies a colorScheme from the parent dashboard, and parks it until the theme provider mounts', () => {
    const { bridge } = make()
    const apply = vi.fn()

    bridge.onMessage(appearance('dark'))
    expect(apply).not.toHaveBeenCalled()

    bridge.attachModeSink(apply)
    expect(apply).toHaveBeenCalledExactlyOnceWith('dark')

    bridge.onMessage(appearance('light'))
    expect(apply).toHaveBeenLastCalledWith('light')
  })

  it('ignores messages from anywhere but window.parent, other sources and bad values', () => {
    const { bridge, submit } = make()
    const apply = vi.fn()

    bridge.attachModeSink(apply)
    bridge.onMessage(appearance('dark', {} as Window))
    bridge.onMessage(appearance('dark', parent, 'evil'))
    bridge.onMessage(appearance('purple'))
    bridge.onMessage(send('hi', {} as Window))
    bridge.onMessage(send('hi', parent, 'evil'))
    bridge.onMessage({ data: null, source: parent } as MessageEvent)

    expect(apply).not.toHaveBeenCalled()
    expect(submit).not.toHaveBeenCalled()
  })

  it('does nothing at all when not framed', () => {
    const top = { location: { search: '' } } as { location: { search: string }; parent?: unknown }

    top.parent = top
    const submit = vi.fn(() => true)
    const bridge = createDashboardBridge({ setTimeout: () => () => {}, submit, win: top as unknown as Window })

    bridge.onMessage({
      data: { source: 'hermes-dashboard', text: 'hi', type: DASHBOARD_SEND_MESSAGE_TYPE },
      source: top
    } as unknown as MessageEvent)
    expect(submit).not.toHaveBeenCalled()
  })

  it('sends a starter prompt as the user, trimmed, and ignores blank text', () => {
    const { bridge, submit } = make()

    bridge.onMessage(send('  Summarise my inbox  '))
    bridge.onMessage(send('   '))
    bridge.onMessage(send(42))

    expect(submit).toHaveBeenCalledExactlyOnceWith('Summarise my inbox')
  })

  it('retries (bounded) while no composer is mounted yet', () => {
    const submit = vi.fn().mockReturnValueOnce(false).mockReturnValueOnce(false).mockReturnValue(true)
    const { bridge, timers } = make(submit)

    bridge.onMessage(send('hello'))
    expect(submit).toHaveBeenCalledTimes(1)
    timers.shift()?.()
    timers.shift()?.()
    expect(submit).toHaveBeenCalledTimes(3)
    expect(timers).toHaveLength(0)
  })

  it('gives up after the retry budget instead of looping forever', () => {
    const { bridge, timers } = make(vi.fn(() => false))
    let guard = 0

    bridge.onMessage(send('hello'))

    while (timers.length && guard++ < 100) {
      timers.shift()?.()
    }

    expect(guard).toBeLessThan(100)
  })

  it('reads the ?theme= hint only when framed', () => {
    const url = (search: string, framedWin = true) => {
      const win = { location: { search } } as { location: { search: string }; parent?: unknown }

      win.parent = framedWin ? {} : win

      return win as unknown as Window
    }

    expect(readDashboardModeFromUrl(url('?theme=dark'))).toBe('dark')
    expect(readDashboardModeFromUrl(url('?theme=hermesos-light'))).toBe('light')
    expect(readDashboardModeFromUrl(url('?theme=light'))).toBe('light')
    expect(readDashboardModeFromUrl(url('?theme=other'))).toBeNull()
    expect(readDashboardModeFromUrl(url('?theme=dark', false))).toBeNull()
  })
})
