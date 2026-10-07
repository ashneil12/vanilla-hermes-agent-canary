// Proves the hosted-web attach path end to end on the RENDERER side: the real
// web shim mints a synthetic path, and Desktop's own `uploadComposerAttachment`
// (remote mode) turns it into the gateway RPCs that stage the bytes. This is
// what replaced the fork's `/api/attachments/upload` endpoint + two core patches.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { uploadComposerAttachment } from '@/app/session/hooks/use-prompt-actions'

describe('web shim + Desktop remote attach', () => {
  beforeEach(async () => {
    vi.resetModules()
    delete (window as unknown as { hermesDesktop?: unknown }).hermesDesktop
    await import('./web-shim')
  })

  afterEach(() => {
    delete (window as unknown as { hermesDesktop?: unknown }).hermesDesktop
    delete (window as unknown as { __HERMES_WEB_CLIENT__?: unknown }).__HERMES_WEB_CLIENT__
  })

  it('sends a non-image browser file through file.attach with its bytes and original name', async () => {
    const path = window.hermesDesktop.getPathForFile(new File(['# hi'], 'notes.md', { type: 'text/markdown' }))
    const requestGateway = vi.fn(async () => ({ attached: true, ref_text: '@file:attachments/notes.md' }) as never)

    const result = await uploadComposerAttachment(
      { id: 'file:notes', kind: 'file', label: 'notes.md', path },
      { remote: true, requestGateway, sessionId: 'sess-1' }
    )

    expect(requestGateway).toHaveBeenCalledTimes(1)
    expect(requestGateway).toHaveBeenCalledWith('file.attach', {
      data_url: 'data:text/markdown;base64,IyBoaQ==',
      name: 'notes.md',
      path,
      session_id: 'sess-1'
    })
    expect(result.refText).toBe('@file:attachments/notes.md')
  })

  it('sends a pasted image through image.attach_bytes', async () => {
    const path = await window.hermesDesktop.saveImageBuffer(new Uint8Array([1, 2, 3]), '.png', 'shot.png')
    const requestGateway = vi.fn(async () => ({ attached: true, path: '/gw/images/shot.png' }) as never)

    const result = await uploadComposerAttachment(
      { id: 'image:shot', kind: 'image', label: 'shot.png', path },
      { remote: true, requestGateway, sessionId: 'sess-1' }
    )

    expect(requestGateway).toHaveBeenCalledWith('image.attach_bytes', {
      content_base64: 'AQID',
      filename: 'shot.png',
      session_id: 'sess-1'
    })
    expect(result.path).toBe('/gw/images/shot.png')
  })

  it('shows Desktop\'s friendly "too large" message for an over-cap file, before any RPC', async () => {
    const big = new File(['x'], 'huge.bin')

    Object.defineProperty(big, 'size', { value: 80 * 1024 * 1024 })
    const path = window.hermesDesktop.getPathForFile(big)
    const requestGateway = vi.fn(async () => ({}) as never)

    await expect(
      uploadComposerAttachment({ id: 'file:big', kind: 'file', label: 'huge.bin', path }, { remote: true, requestGateway, sessionId: 'sess-1' })
    ).rejects.toThrow(/huge\.bin.*too large to upload to the remote gateway \(max 50 MB\)/)
    expect(requestGateway).not.toHaveBeenCalled()
  })
})
