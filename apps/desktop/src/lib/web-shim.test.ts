import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

describe('hosted web connection routing', () => {
  beforeEach(() => {
    vi.resetModules()
    window.localStorage.clear()
    window.sessionStorage.clear()
    delete (window as unknown as { hermesDesktop?: unknown }).hermesDesktop
    delete (window as unknown as { __HERMES_WEB_CLIENT__?: unknown }).__HERMES_WEB_CLIENT__
    document.getElementById('hermesos-skin')?.remove()
  })

  afterEach(() => {
    delete (window as unknown as { hermesDesktop?: unknown }).hermesDesktop
    delete (window as unknown as { __HERMES_WEB_CLIENT__?: unknown }).__HERMES_WEB_CLIENT__
    document.getElementById('hermesos-skin')?.remove()
  })

  it('reuses the primary socket for named profiles', async () => {
    await import('./web-shim')

    const primary = await window.hermesDesktop.getConnection()
    const epifanio = await window.hermesDesktop.getConnection('  epifanio  ')

    expect(primary.sharedPrimary).toBeUndefined()
    expect(primary.profile).toBeUndefined()
    expect(epifanio).toMatchObject({
      baseUrl: primary.baseUrl,
      wsUrl: primary.wsUrl,
      profile: 'epifanio',
      sharedPrimary: true
    })
  })
})
