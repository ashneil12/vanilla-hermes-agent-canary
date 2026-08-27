import { GatewayTransportError, JsonRpcGatewayClient, JsonRpcGatewayError } from '@hermes/shared'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

class ControlledSocket extends EventTarget {
  static OPEN = 1
  static CLOSED = 3
  readyState = 0
  send = vi.fn()
  close = vi.fn(() => {
    this.readyState = ControlledSocket.CLOSED
    this.dispatchEvent(new Event('close'))
  })

  open() {
    this.readyState = ControlledSocket.OPEN
    this.dispatchEvent(new Event('open'))
  }

  fail() {
    this.readyState = ControlledSocket.CLOSED
    this.dispatchEvent(new Event('error'))
  }
}

describe('JsonRpcGatewayClient pre-handshake transport failures', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('WebSocket', ControlledSocket)
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it.each(['error', 'timeout'] as const)('tags a handshake %s and can connect again', async failure => {
    const sockets: ControlledSocket[] = []

    const client = new JsonRpcGatewayClient({
      connectErrorMessage: 'Could not connect to Hermes gateway',
      connectTimeoutMs: 1_000,
      socketFactory: () => {
        const socket = new ControlledSocket()
        sockets.push(socket)

        return socket as unknown as WebSocket
      }
    })

    const failed = client.connect('wss://gateway.example/api/ws').catch(error => error)

    if (failure === 'error') {
      sockets[0].fail()
    } else {
      await vi.advanceTimersByTimeAsync(1_000)
      expect(sockets[0].close).toHaveBeenCalledOnce()
    }

    const error = await failed
    expect(error).toBeInstanceOf(GatewayTransportError)
    expect(error.message).toBe('Could not connect to Hermes gateway')
    expect(client.connectionState).toBe('error')
    expect(vi.getTimerCount()).toBe(0)

    const connected = client.connect('wss://gateway.example/api/ws')
    // A late event on the abandoned handshake must not open the new socket.
    sockets[0].open()
    expect(client.connectionState).toBe('connecting')
    sockets[1].open()
    await connected
    expect(client.connectionState).toBe('open')
    expect(vi.getTimerCount()).toBe(0)
    client.close()
  })

  it.each(['https://gateway.example/api/ws', 'ws://', ''])('does not tag invalid URL %j as transport', async url => {
    const socketFactory = vi.fn()
    const client = new JsonRpcGatewayClient({ socketFactory })
    const error = await client.connect(url).catch(error => error)

    expect(error).toBeInstanceOf(Error)
    expect(error).not.toBeInstanceOf(GatewayTransportError)
    expect(socketFactory).not.toHaveBeenCalled()
    expect(client.connectionState).toBe('idle')
  })

  it('does not tag a synchronous WebSocket construction error as transport', async () => {
    const configError = new DOMException('Blocked URL', 'SecurityError')

    const client = new JsonRpcGatewayClient({
      socketFactory: () => {
        throw configError
      }
    })

    await expect(client.connect('wss://gateway.example/api/ws')).rejects.toBe(configError)
    expect(configError).not.toBeInstanceOf(GatewayTransportError)
  })

  it('keeps post-handshake RPC and connection-closed errors separate', async () => {
    const socket = new ControlledSocket()
    const client = new JsonRpcGatewayClient({ socketFactory: () => socket as unknown as WebSocket })
    const connected = client.connect('wss://gateway.example/api/ws')
    socket.open()
    await connected

    const rejectedRpc = client.request('session.list').catch(error => error)
    const request = JSON.parse(socket.send.mock.calls[0][0]) as { id: string }
    socket.dispatchEvent(
      new MessageEvent('message', {
        data: JSON.stringify({ id: request.id, error: { code: 401, message: 'Unauthorized' } })
      })
    )
    const rpcError = await rejectedRpc
    expect(rpcError).toBeInstanceOf(JsonRpcGatewayError)
    expect(rpcError).not.toBeInstanceOf(GatewayTransportError)

    const pending = client.request('session.list').catch(error => error)
    socket.close()
    const closedError = await pending
    expect(closedError).toEqual(expect.objectContaining({ message: 'WebSocket closed' }))
    expect(closedError).not.toBeInstanceOf(GatewayTransportError)
    expect(client.connectionState).toBe('closed')
    expect(vi.getTimerCount()).toBe(0)
  })
})
