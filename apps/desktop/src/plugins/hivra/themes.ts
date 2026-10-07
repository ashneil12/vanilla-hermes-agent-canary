import { DEFAULT_TYPOGRAPHY, monoTheme } from '@/themes/presets'
import type { DesktopTheme } from '@/themes/types'

/** Name painted on a hosted-web first run (see `seedDefaultSkin` in plugin.tsx). */
export const HIVRA_SKIN_NAME = 'hivra'

const HIVRA_RED = '#ff2c2d'
const HIVRA_RED_DARK = '#ff3a3b'

export const hivraTheme: DesktopTheme = {
  name: HIVRA_SKIN_NAME,
  label: 'Hivra',
  description: 'Matches the Hivra dashboard — red signal, light & dark',
  colors: {
    background: '#fdfcf9',
    foreground: '#1a1a1a',
    card: '#ffffff',
    cardForeground: '#1a1a1a',
    muted: '#f3f1ec',
    mutedForeground: '#6f6d68',
    popover: '#ffffff',
    popoverForeground: '#1a1a1a',
    primary: HIVRA_RED,
    primaryForeground: '#ffffff',
    secondary: '#efece4',
    secondaryForeground: '#242424',
    accent: '#fdeaea',
    accentForeground: '#1a1a1a',
    border: 'rgba(26, 26, 26, 0.10)',
    input: 'rgba(26, 26, 26, 0.16)',
    ring: HIVRA_RED,
    midground: HIVRA_RED,
    composerRing: HIVRA_RED,
    destructive: '#c0392b',
    destructiveForeground: '#ffffff',
    sidebarBackground: '#f7f4ee',
    sidebarBorder: 'rgba(26, 26, 26, 0.08)',
    userBubble: '#efece4',
    userBubbleBorder: 'rgba(26, 26, 26, 0.12)'
  },
  darkColors: {
    background: '#0d0d0d',
    foreground: '#fdfcf9',
    card: '#141414',
    cardForeground: '#fdfcf9',
    muted: '#1a1a1a',
    mutedForeground: 'rgba(253, 252, 249, 0.52)',
    popover: '#161616',
    popoverForeground: '#fdfcf9',
    primary: HIVRA_RED_DARK,
    primaryForeground: '#ffffff',
    secondary: '#1f1f1f',
    secondaryForeground: '#e8e6e1',
    accent: '#2a1414',
    accentForeground: '#fdfcf9',
    border: 'rgba(253, 252, 249, 0.12)',
    input: 'rgba(253, 252, 249, 0.16)',
    ring: HIVRA_RED_DARK,
    midground: HIVRA_RED_DARK,
    composerRing: HIVRA_RED_DARK,
    destructive: '#e0524a',
    destructiveForeground: '#ffffff',
    sidebarBackground: '#0a0a0a',
    sidebarBorder: 'rgba(253, 252, 249, 0.08)',
    userBubble: '#1a1a1a',
    userBubbleBorder: 'rgba(253, 252, 249, 0.14)'
  },
  typography: {
    fontSans: `"Space Grotesk", ${DEFAULT_TYPOGRAPHY.fontSans}`,
    fontMono: `"Space Mono", ${DEFAULT_TYPOGRAPHY.fontMono}`,
    fontUrl:
      'https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Space+Mono:wght@400;700&display=swap'
  }
}

/** Kept registered so a skin name persisted by an earlier build still resolves. */
export const hermesOSDarkTheme: DesktopTheme = {
  name: 'hermesos-dark',
  label: 'HermesOS Dark',
  description: 'The signature Hermes dark — clean grayscale',
  colors: { ...monoTheme.colors }
}
