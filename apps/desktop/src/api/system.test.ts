import { beforeEach, describe, expect, it, vi } from 'vitest'

import { openBackupDownload } from './system'

describe('backup download', () => {
  beforeEach(() => {
    window.hermesDesktop = {
      getConnection: vi.fn(async () => ({
        baseUrl: 'https://agent.example.test/desktop/',
        mode: 'remote',
        source: 'env',
        token: 'session token',
        wsUrl: 'wss://agent.example.test/desktop/api/ws'
      })),
      openExternal: vi.fn(async () => undefined)
    } as unknown as Window['hermesDesktop']
  })

  it('opens the streaming backup endpoint with encoded archive and auth', async () => {
    await openBackupDownload('/home/hermes/.hermes/backups/backup one.zip')

    expect(window.hermesDesktop.openExternal).toHaveBeenCalledOnce()
    const opened = new URL(vi.mocked(window.hermesDesktop.openExternal).mock.calls[0][0])
    expect(`${opened.origin}${opened.pathname}`).toBe('https://agent.example.test/desktop/api/ops/backup/download')
    expect(opened.searchParams.get('archive')).toBe('/home/hermes/.hermes/backups/backup one.zip')
    expect(opened.searchParams.get('token')).toBe('session token')
  })
})
