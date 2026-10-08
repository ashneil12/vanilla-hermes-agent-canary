import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { WEB_ATTACH_MAX_BYTES, WEB_FILE_ROOT } from './web-files'

type Bridge = Window['hermesDesktop'] & {
  getAdminPanelUrl: () => string
  openAdminPanel: () => boolean
}

const bridge = () => window.hermesDesktop as Bridge

describe('hosted web connection routing', () => {
  beforeEach(() => {
    vi.resetModules()
    window.localStorage.clear()
    window.sessionStorage.clear()
    delete (window as unknown as { hermesDesktop?: unknown }).hermesDesktop
    delete (window as unknown as { __HERMES_WEB_CLIENT__?: unknown }).__HERMES_WEB_CLIENT__
  })

  afterEach(() => {
    delete (window as unknown as { hermesDesktop?: unknown }).hermesDesktop
    delete (window as unknown as { __HERMES_WEB_CLIENT__?: unknown }).__HERMES_WEB_CLIENT__
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

  it('is a no-op when the Electron preload already defined the bridge', async () => {
    const preload = { getConnection: vi.fn() }

    ;(window as unknown as { hermesDesktop: unknown }).hermesDesktop = preload
    await import('./web-shim')

    expect(window.hermesDesktop).toBe(preload)
    expect((window as unknown as { __HERMES_WEB_CLIENT__?: boolean }).__HERMES_WEB_CLIENT__).toBeUndefined()
  })

  it('marks the page as the hosted web client (the plugin and the composer picker key off it)', async () => {
    await import('./web-shim')

    expect((window as unknown as { __HERMES_WEB_CLIENT__?: boolean }).__HERMES_WEB_CLIENT__).toBe(true)
  })

  it('leaves Electron-only bridge keys undefined so feature detection hides their UI', async () => {
    await import('./web-shim')

    // The renderer gates these surfaces on `window.hermesDesktop?.<key>` /
    // `typeof ...<key> === 'function'`; a catch-all no-op would switch them on.
    for (const key of ['cloud', 'connections', 'quickEntry', 'openWindow', 'openSessionWindow', 'zoom', 'renamePath']) {
      expect((window.hermesDesktop as unknown as Record<string, unknown>)[key], key).toBeUndefined()
    }
  })

  it('implements the required keys the renderer calls without a feature check', async () => {
    await import('./web-shim')

    await expect(bridge().readClipboard()).resolves.toBe('')
    await expect(bridge().profile.set('coder')).resolves.toMatchObject({ profile: 'coder' })
    await expect(bridge().profile.set(null)).resolves.toMatchObject({ profile: 'default' })
    expect(bridge().profile.getDefault).toBeUndefined()
  })

  it('builds the Admin Panel URL with the handed-off token in the fragment only', async () => {
    window.location.hash = '#iframe_token=abc%20123'
    await import('./web-shim')

    expect(bridge().getAdminPanelUrl()).toBe('/dash/#iframe_token=abc%20123')
    // the token is scrubbed from the visible URL after being captured
    expect(window.location.hash).toBe('')
  })

  it('openAdminPanel reports whether the browser allowed the new tab', async () => {
    await import('./web-shim')
    const open = vi
      .spyOn(window, 'open')
      .mockReturnValueOnce({} as Window)
      .mockReturnValueOnce(null)

    expect(bridge().openAdminPanel()).toBe(true)
    expect(bridge().openAdminPanel()).toBe(false)
    expect(open).toHaveBeenCalledWith('/dash/', '_blank', 'noopener,noreferrer')
    open.mockRestore()
  })
})

describe('hosted web attachments (synthetic paths, no upload endpoint)', () => {
  beforeEach(() => {
    vi.resetModules()
    delete (window as unknown as { hermesDesktop?: unknown }).hermesDesktop
  })

  afterEach(() => {
    delete (window as unknown as { hermesDesktop?: unknown }).hermesDesktop
    delete (window as unknown as { __HERMES_WEB_CLIENT__?: unknown }).__HERMES_WEB_CLIENT__
    vi.unstubAllGlobals()
  })

  it('gives a File a stable synthetic path whose basename is the file name', async () => {
    await import('./web-shim')
    const file = new File(['hello'], 'notes.md', { type: 'text/markdown' })
    const path = window.hermesDesktop.getPathForFile(file)

    expect(path.startsWith(`${WEB_FILE_ROOT}/`)).toBe(true)
    expect(path.split('/').pop()).toBe('notes.md')
    expect(window.hermesDesktop.getPathForFile(file)).toBe(path)
  })

  it('never lets a hostile file name escape its slot', async () => {
    await import('./web-shim')

    for (const name of ['../../etc/passwd', '..', '.', '']) {
      const path = window.hermesDesktop.getPathForFile(new File(['x'], name))
      const segments = path.slice(WEB_FILE_ROOT.length + 1).split('/')

      expect(path.startsWith(`${WEB_FILE_ROOT}/`)).toBe(true)
      expect(segments).toHaveLength(2)
      expect(segments).not.toContain('..')
      expect(segments).not.toContain('.')
    }
  })

  it('serves the bytes back as a data URL for Desktop remote attach (file.attach data_url)', async () => {
    await import('./web-shim')
    const path = window.hermesDesktop.getPathForFile(new File(['hello'], 'notes.md', { type: 'text/markdown' }))
    const dataUrl = await window.hermesDesktop.readFileDataUrlForAttach!(path)

    expect(dataUrl).toBe('data:text/markdown;base64,aGVsbG8=')
    await expect(window.hermesDesktop.readFileDataUrl(path)).resolves.toBe(dataUrl)
  })

  it('returns an empty string for paths it did not mint', async () => {
    await import('./web-shim')

    await expect(window.hermesDesktop.readFileDataUrl('/etc/passwd')).resolves.toBe('')
    await expect(window.hermesDesktop.readFileDataUrl(`${WEB_FILE_ROOT}/nope/x.txt`)).resolves.toBe('')
  })

  it('rejects over-cap files with the Electron "too large" message shape', async () => {
    await import('./web-shim')
    const big = new File(['x'], 'big.bin')

    Object.defineProperty(big, 'size', { value: WEB_ATTACH_MAX_BYTES + 1 })
    const path = window.hermesDesktop.getPathForFile(big)

    await expect(window.hermesDesktop.readFileDataUrl(path)).rejects.toThrow(
      `file is too large (${WEB_ATTACH_MAX_BYTES + 1} bytes; limit ${WEB_ATTACH_MAX_BYTES} bytes)`
    )
  })

  it('stores pasted / dropped image bytes under a synthetic path (no network)', async () => {
    const fetchSpy = vi.fn()

    vi.stubGlobal('fetch', fetchSpy)
    await import('./web-shim')
    const path = await window.hermesDesktop.saveImageBuffer(new Uint8Array([1, 2, 3]), '.png', 'shot.png')

    expect(path.endsWith('/shot.png')).toBe(true)
    await expect(window.hermesDesktop.readFileDataUrl(path)).resolves.toBe('data:image/png;base64,AQID')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('selectPaths turns the picked files into synthetic paths', async () => {
    await import('./web-shim')
    const picked = new File(['a'], 'a.txt')

    const click = vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(function (this: HTMLInputElement) {
      Object.defineProperty(this, 'files', { value: [picked] })
      this.dispatchEvent(new Event('change'))
    })

    const paths = await window.hermesDesktop.selectPaths()

    expect(paths).toEqual([window.hermesDesktop.getPathForFile(picked)])
    click.mockRestore()
  })
})
