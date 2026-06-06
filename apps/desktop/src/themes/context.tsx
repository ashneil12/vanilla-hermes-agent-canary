/**
 * Desktop theme context.
 *
 * Applies the active theme as CSS custom properties on :root so every
 * Tailwind utility that references a color or font-family token picks up
 * the change automatically.
 *
 * Mode (light/dark/system) controls brightness; skin controls accent.
 * The two are persisted independently. Shift+X toggles light/dark.
 */

import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import { matchesQuery, useMediaQuery } from '@/hooks/use-media-query'

import { BUILTIN_THEME_LIST, BUILTIN_THEMES, DEFAULT_SKIN_NAME, DEFAULT_TYPOGRAPHY, nousTheme } from './presets'
import type { DesktopTheme, DesktopThemeColors } from './types'

const SKIN_KEY = 'hermes-desktop-theme-v2'
const MODE_KEY = 'hermes-desktop-mode-v1'
const RETIRED_SKINS = new Set(['nous-light', 'default', 'gold'])

/**
 * Dashboard appearance bridge. When this app is embedded as an iframe in the
 * Hermes dashboard, the dashboard posts {colorScheme: 'light' | 'dark'} on
 * mount and on every light/dark toggle, and pre-encodes ?theme= on the iframe
 * URL so the first paint matches. Mirrors WEBUI_DASHBOARD_APPEARANCE_MESSAGE_TYPE
 * in hermesdeploy/dashboard/src/lib/webui-appearance.ts.
 */
const DASHBOARD_APPEARANCE_MESSAGE_TYPE = 'hermes-dashboard:appearance'

export type ThemeMode = 'light' | 'dark' | 'system'

/** Mode hint from the dashboard's `?theme=` query param, when in an iframe. */
function readDashboardModeFromUrl(): ThemeMode | null {
  if (typeof window === 'undefined' || window === window.parent) {
    return null
  }

  const theme = new URLSearchParams(window.location.search).get('theme')

  if (theme === 'dark') return 'dark'
  if (theme === 'hermesos-light' || theme === 'light') return 'light'

  return null
}

function readInitialMode(): ThemeMode {
  if (typeof window === 'undefined') {
    return 'light'
  }

  const dashboardMode = readDashboardModeFromUrl()

  if (dashboardMode) {
    return dashboardMode
  }

  return (window.localStorage.getItem(MODE_KEY) as ThemeMode) ?? 'light'
}

const INJECTED_FONT_URLS = new Set<string>()

const resolveMode = (mode: ThemeMode, systemDark = matchesQuery('(prefers-color-scheme: dark)')): 'light' | 'dark' =>
  mode === 'system' ? (systemDark ? 'dark' : 'light') : mode

const normalizeSkin = (name: string | null | undefined): string =>
  name && BUILTIN_THEMES[name] && !RETIRED_SKINS.has(name) ? name : DEFAULT_SKIN_NAME

/**
 * Per-mode default skin, used only when the user hasn't explicitly picked one.
 * Light reads best on Nous (glass neutrals + blue accent); dark reads best on
 * Mono (clean grayscale) rather than the saturated Nous-blue dark palette.
 * Once the user picks a skin it's persisted and overrides this for both modes.
 */
const MODE_DEFAULT_SKINS: Record<'light' | 'dark', string> = { light: 'nous', dark: 'mono' }

/** A persisted skin choice, or null when nothing valid is stored (→ auto). */
function readStoredSkin(): string | null {
  if (typeof window === 'undefined') {
    return null
  }

  const raw = window.localStorage.getItem(SKIN_KEY)

  return raw && BUILTIN_THEMES[raw] && !RETIRED_SKINS.has(raw) ? raw : null
}

/** Effective skin name: the explicit choice, else the mode-aware default. */
const resolveSkin = (stored: string | null, mode: 'light' | 'dark'): string =>
  stored ?? MODE_DEFAULT_SKINS[mode]

// ─── Color math (for synthesised light variants of dark-only skins) ────────

function hexToRgb(hex: string): [number, number, number] | null {
  const clean = hex.trim().replace(/^#/, '')

  if (!/^[0-9a-f]{6}$/i.test(clean)) {
    return null
  }

  return [0, 2, 4].map(i => parseInt(clean.slice(i, i + 2), 16)) as [number, number, number]
}

const rgbToHex = ([r, g, b]: [number, number, number]) =>
  `#${[r, g, b].map(n => Math.round(n).toString(16).padStart(2, '0')).join('')}`

function mix(a: string, b: string, amount: number): string {
  const ar = hexToRgb(a)
  const br = hexToRgb(b)

  return ar && br
    ? rgbToHex([ar[0] + (br[0] - ar[0]) * amount, ar[1] + (br[1] - ar[1]) * amount, ar[2] + (br[2] - ar[2]) * amount])
    : a
}

function readableOn(hex: string): string {
  const rgb = hexToRgb(hex)

  if (!rgb) {
    return '#ffffff'
  }

  const [r, g, b] = rgb.map(v => {
    const c = v / 255

    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })

  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.58 ? '#161616' : '#ffffff'
}

function synthLightColors(seed: DesktopTheme): DesktopThemeColors {
  const accent = seed.colors.ring || seed.colors.primary
  const soft = mix('#ffffff', accent, 0.1)
  const softer = mix('#ffffff', accent, 0.06)
  const border = mix('#ececef', accent, 0.14)
  const midground = seed.colors.midground ?? accent

  return {
    background: '#ffffff',
    foreground: '#161616',
    card: '#ffffff',
    cardForeground: '#161616',
    muted: softer,
    mutedForeground: mix('#6b6b70', accent, 0.16),
    popover: '#ffffff',
    popoverForeground: '#161616',
    primary: accent,
    primaryForeground: readableOn(accent),
    secondary: soft,
    secondaryForeground: mix('#2a2a2a', accent, 0.34),
    accent: soft,
    accentForeground: mix('#2a2a2a', accent, 0.34),
    border,
    input: mix('#e2e2e6', accent, 0.18),
    ring: accent,
    midground,
    midgroundForeground: readableOn(midground),
    destructive: '#b94a3a',
    destructiveForeground: '#ffffff',
    sidebarBackground: mix('#fafafa', accent, 0.05),
    sidebarBorder: border,
    userBubble: soft,
    userBubbleBorder: border
  }
}

/** Returns the seed palette for a given skin + mode (no overrides applied). */
export function getBaseColors(skinName: string, mode: 'light' | 'dark'): DesktopThemeColors {
  const seed = BUILTIN_THEMES[skinName] ?? nousTheme

  if (mode === 'dark') {
    return seed.darkColors ?? seed.colors
  }

  return seed.darkColors ? seed.colors : synthLightColors(seed)
}

function deriveTheme(skinName: string, mode: 'light' | 'dark'): DesktopTheme {
  const seed = BUILTIN_THEMES[skinName] ?? nousTheme

  return {
    ...seed,
    name: `${skinName}-${mode}`,
    label: `${seed.label} ${mode === 'light' ? 'Light' : 'Dark'}`,
    description: `${seed.label} ${mode} palette`,
    colors: getBaseColors(skinName, mode)
  }
}

/**
 * Some palettes intentionally keep a bright background even when
 * `mode === 'dark'`, so we shouldn't apply the `.dark` class. Decide from
 * the actual background luminance.
 */
function renderedModeFor(colors: DesktopThemeColors, mode: 'light' | 'dark'): 'light' | 'dark' {
  const rgb = hexToRgb(colors.background)

  if (!rgb) {
    return mode
  }

  const [r, g, b] = rgb.map(v => v / 255)

  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.5 ? 'light' : 'dark'
}

// ─── CSS application ────────────────────────────────────────────────────────

// Per-mode mix knobs. Light/dark fallbacks live in styles.css `:root` /
// `:root.dark`; setting them inline keeps active-skin overrides surviving
// the boot-time paint.
const mixesFor = (isDark: boolean): Record<string, string> => ({
  '--theme-mix-chrome': isDark ? '74%' : '92%',
  '--theme-mix-sidebar': '100%',
  '--theme-mix-card': isDark ? '38%' : '22%',
  '--theme-mix-elevated': isDark ? '46%' : '28%',
  '--theme-mix-bubble': isDark ? '46%' : '0%'
})

function applyTheme(theme: DesktopTheme, mode: 'light' | 'dark') {
  if (typeof document === 'undefined') {
    return
  }

  const root = document.documentElement
  const c = theme.colors
  const typo = { ...DEFAULT_TYPOGRAPHY, ...nousTheme.typography, ...theme.typography }
  const rendered = renderedModeFor(c, mode)
  const isDark = rendered === 'dark'
  const midground = c.midground ?? c.ring
  const skinName = theme.name.endsWith(`-${mode}`) ? theme.name.slice(0, -mode.length - 1) : theme.name

  root.style.setProperty('color-scheme', rendered)
  root.dataset.hermesTheme = skinName
  root.dataset.hermesMode = rendered
  root.classList.toggle('dark', isDark)

  // Brand seeds feed every glass + shadcn token via `color-mix()` in styles.css.
  const seeds: Record<string, string> = {
    '--theme-foreground': c.foreground,
    '--theme-primary': c.primary,
    '--theme-secondary': c.secondary,
    '--theme-accent-soft': c.accent,
    '--theme-midground': midground,
    '--theme-warm': c.primary,
    '--theme-background-seed': c.background,
    '--theme-sidebar-seed': c.sidebarBackground ?? c.background,
    '--theme-card-seed': c.card,
    '--theme-elevated-seed': c.popover,
    '--theme-bubble-seed': c.userBubble ?? c.popover
  }

  // shadcn/Tailwind tokens that aren't derived from the seed chain.
  const palette: Record<string, string> = {
    '--dt-primary-foreground': c.primaryForeground,
    '--dt-secondary-foreground': c.secondaryForeground,
    '--dt-accent-foreground': c.accentForeground,
    '--dt-border': c.border,
    '--dt-input': c.input,
    '--dt-ring': c.ring,
    '--dt-muted': c.muted,
    '--dt-midground-foreground': c.midgroundForeground ?? readableOn(midground),
    '--dt-composer-ring': c.composerRing ?? midground,
    '--dt-destructive': c.destructive,
    '--dt-destructive-foreground': c.destructiveForeground,
    '--dt-sidebar-border': c.sidebarBorder ?? c.border,
    '--dt-user-bubble-border': c.userBubbleBorder ?? c.border,
    '--dt-font-sans': typo.fontSans,
    '--dt-font-mono': typo.fontMono,
    '--noise-opacity-mul': isDark ? 'calc(0.04 / 0.21)' : 'calc(0.34 / 0.21)'
  }

  for (const [k, v] of Object.entries({ ...seeds, ...mixesFor(isDark), ...palette })) {
    root.style.setProperty(k, v)
  }

  window.hermesDesktop?.setTitleBarTheme?.({
    background: c.background,
    foreground: c.foreground
  })

  if (typo.fontUrl && !INJECTED_FONT_URLS.has(typo.fontUrl)) {
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = typo.fontUrl
    link.dataset.hermesThemeFont = 'true'
    document.head.appendChild(link)
    INJECTED_FONT_URLS.add(typo.fontUrl)
  }
}

// Boot-time paint to avoid a flash before <ThemeProvider> mounts.
if (typeof window !== 'undefined') {
  const mode = readInitialMode()
  const resolved = resolveMode(mode)
  const skin = resolveSkin(readStoredSkin(), resolved)
  applyTheme(deriveTheme(skin, resolved), resolved)
}

// ─── Context ────────────────────────────────────────────────────────────────

interface ThemeContextValue {
  theme: DesktopTheme
  themeName: string
  mode: ThemeMode
  resolvedMode: 'light' | 'dark'
  availableThemes: Array<{ name: string; label: string; description: string }>
  setTheme: (name: string) => void
  setMode: (mode: ThemeMode) => void
}

const SKIN_LIST = BUILTIN_THEME_LIST.map(({ name, label, description }) => ({ name, label, description }))

const ThemeContext = createContext<ThemeContextValue>({
  theme: nousTheme,
  themeName: DEFAULT_SKIN_NAME,
  mode: 'light',
  resolvedMode: 'light',
  availableThemes: SKIN_LIST,
  setTheme: () => {},
  setMode: () => {}
})

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [storedSkin, setStoredSkin] = useState<string | null>(readStoredSkin)

  const [mode, setModeState] = useState<ThemeMode>(readInitialMode)

  const systemDark = useMediaQuery('(prefers-color-scheme: dark)')
  const resolvedMode = resolveMode(mode, systemDark)
  // Effective skin: an explicit pick wins; otherwise the mode-aware default
  // (Nous in light, Mono in dark), so it flips with the mode until chosen.
  const themeName = resolveSkin(storedSkin, resolvedMode)
  const activeTheme = useMemo(() => deriveTheme(themeName, resolvedMode), [themeName, resolvedMode])

  useEffect(() => applyTheme(activeTheme, resolvedMode), [activeTheme, resolvedMode])

  const setTheme = useCallback((name: string) => {
    const next = normalizeSkin(name)
    setStoredSkin(next)
    window.localStorage.setItem(SKIN_KEY, next)
  }, [])

  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next)
    window.localStorage.setItem(MODE_KEY, next)
  }, [])

  // Dashboard ↔ chat color-mode sync. When the dashboard hosts us in an
  // iframe and the user toggles its light/dark switch, the dashboard posts
  // an appearance message; we honor the colorScheme to keep the chat in
  // step. Only mode syncs — the user's theme/skin pick stays untouched.
  useEffect(() => {
    if (typeof window === 'undefined' || window === window.parent) {
      return
    }

    const onMessage = (event: MessageEvent) => {
      if (event.source !== window.parent) return

      const data = event.data as
        | { type?: unknown; source?: unknown; appearance?: { colorScheme?: unknown } }
        | null
        | undefined

      if (
        !data ||
        typeof data !== 'object' ||
        data.type !== DASHBOARD_APPEARANCE_MESSAGE_TYPE ||
        data.source !== 'hermes-dashboard'
      ) {
        return
      }

      const colorScheme = data.appearance?.colorScheme

      if (colorScheme === 'dark' || colorScheme === 'light') {
        setMode(colorScheme)
      }
    }

    window.addEventListener('message', onMessage)

    return () => window.removeEventListener('message', onMessage)
  }, [setMode])

  // Shift+X toggles light/dark anywhere outside an editable field.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const t = event.target as HTMLElement | null

      const editing =
        t?.isContentEditable ||
        t instanceof HTMLInputElement ||
        t instanceof HTMLTextAreaElement ||
        t instanceof HTMLSelectElement

      if (editing || event.repeat || event.altKey || event.ctrlKey || event.metaKey) {
        return
      }

      if (event.shiftKey && event.code === 'KeyX') {
        setMode(resolvedMode === 'dark' ? 'light' : 'dark')
      }
    }

    window.addEventListener('keydown', onKeyDown)

    return () => window.removeEventListener('keydown', onKeyDown)
  }, [resolvedMode, setMode])

  const value = useMemo<ThemeContextValue>(
    () => ({ theme: activeTheme, themeName, mode, resolvedMode, availableThemes: SKIN_LIST, setTheme, setMode }),
    [activeTheme, themeName, mode, resolvedMode, setTheme, setMode]
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export const useTheme = (): ThemeContextValue => useContext(ThemeContext)

/** Sync the desktop skin with the active Hermes backend theme on connect. */
export function useSyncThemeFromBackend(backendThemeName: string | undefined, setTheme: (name: string) => void) {
  useEffect(() => {
    if (backendThemeName && BUILTIN_THEMES[backendThemeName]) {
      setTheme(backendThemeName)
    }
  }, [backendThemeName, setTheme])
}
