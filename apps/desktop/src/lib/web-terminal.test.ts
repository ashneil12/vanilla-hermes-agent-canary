import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createWebTerminal } from './web-terminal'

type Options = Parameters<typeof createWebTerminal>[0]
type Request = Parameters<ReturnType<Options['captureRequest']>>[0]

class FakeSocket extends EventTarget {
  static instances: FakeSocket[] = []
  readonly url: string
  readyState = 0
  close = vi.fn(() => { this.readyState = 3 })

  constructor(url: string) {
    super()
    this.url = url
    FakeSocket.instances.push(this)
  }

  open() {
    this.readyState = 1
    this.dispatchEvent(new Event('open'))
  }

  message(value: unknown) {
    this.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(value) }))
  }

  disconnect() {
    this.readyState = 3
    this.dispatchEvent(new Event('close'))
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })

  return { promise, resolve, reject }
}

async function flush() {
  for (let i = 0; i < 24; i += 1) {
    await Promise.resolve()
  }
}

function startReply(id = 'native-1', patch: Record<string, unknown> = {}) {
  return {
    ok: true,
    sessionKey: id,
    sessionToken: `session-secret-${id}`,
    cwd: '/workspace',
    shell: 'bash',
    webSocketPath: `/_sidecar/api/terminal/ws?token=ticket-${id}&includeScrollback=1`,
    ...patch
  }
}

function harness(handler?: (request: Request) => Promise<unknown>) {
  let nextId = 0

  const request = vi.fn(async (params: Request) => {
    if (handler) {
      return handler(params)
    }

    return (params.body as { action: string }).action === 'start'
      ? startReply(`native-${++nextId}`)
      : { ok: true, cwd: null }
  })

  const getProfile = vi.fn<() => string | null>(() => null)
  const getConnectionId = vi.fn<() => string | null>(() => null)
  const captureRequest = vi.fn(() => async <T>(params: Request) => await request(params) as T)
  const terminal = createWebTerminal({ captureRequest, getProfile, getConnectionId })
  const calls = (action: string) => request.mock.calls.map(([req]) => req).filter(req => (req.body as { action: string }).action === action)

  async function start() {
    const pending = terminal.start()
    await flush()
    const socket = FakeSocket.instances.at(-1)!
    socket.open()
    const session = await pending

    return { session, socket }
  }

  return { terminal, request, calls, getProfile, getConnectionId, captureRequest, start }
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('WebSocket', FakeSocket)
  FakeSocket.instances = []
})

afterEach(async () => {
  window.dispatchEvent(new Event('pagehide'))
  await flush()
  await vi.runAllTimersAsync()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('browser terminal session capability', () => {
  it('waits for the ticket-authenticated socket and exposes no credentials in the desktop session', async () => {
    const h = harness()
    const settled = vi.fn()

    const pending = h.terminal.start({ cwd: '/workspace/project', cols: 110, rows: 32 }).then(value => { settled();

 return value })

    await flush()
    expect(settled).not.toHaveBeenCalled()
    expect(h.calls('start')[0]).toMatchObject({
      path: '/api/desktop-terminal', method: 'POST', timeoutMs: 20_000,
      body: { action: 'start', cols: 110, rows: 32, cwd: '/workspace/project', profile: 'default' }
    })
    const socket = FakeSocket.instances[0]
    const url = new URL(socket.url)
    expect(url.host).toBe(window.location.host)
    expect(url.protocol).toBe('ws:')
    expect(url.pathname).toBe('/_sidecar/api/terminal/ws')
    expect([...url.searchParams]).toEqual([['token', 'ticket-native-1'], ['includeScrollback', '1']])
    socket.open()
    await expect(pending).resolves.toEqual({ id: 'native-1', cwd: '/workspace', shell: 'bash' })
    expect(h.calls('start')).toHaveLength(1)
  })

  it('uses wss for an https origin without accepting a server-specified host', async () => {
    const browser = window
    vi.stubGlobal('window', new Proxy(browser, {
      get(target, key) { return key === 'location' ? { origin: 'https://terminal.example' } : Reflect.get(target, key) }
    }))
    const h = harness()
    const { session, socket } = await h.start()
    expect(socket.url).toBe('wss://terminal.example/_sidecar/api/terminal/ws?token=ticket-native-1&includeScrollback=1')
    await h.terminal.dispose(session.id)
  })

  it.each([
    'wss://evil.example/_sidecar/api/terminal/ws?token=stolen',
    'ws://localhost/_sidecar/api/terminal/ws?token=t',
    '//evil.example/_sidecar/api/terminal/ws?token=t',
    '/desktop/api/terminal/ws?token=t',
    '/_sidecar/api/terminal/../ws?token=t',
    '/_sidecar/api/terminal/ws',
    '/_sidecar/api/terminal/ws?token=',
    '/_sidecar/api/terminal/ws?token=a&token=b',
    '/_sidecar/api/terminal/ws?token=a&api_key=b',
    '/_sidecar/api/terminal/ws?token=a#fragment',
    '/_sidecar/api/terminal/ws?token=a&includeScrollback=0',
    '/_sidecar/api/terminal/ws?token=a&includeScrollback=1&includeScrollback=1',
    '/_sidecar/api/terminal/ws?token=a\\evil',
    null
  ])('rejects unsafe/malformed socket path %s and stops only the allocated session', async webSocketPath => {
    const h = harness(async request => (request.body as { action: string }).action === 'start'
      ? startReply('native-own', { webSocketPath }) : { ok: true })

    await expect(h.terminal.start()).rejects.toThrow('invalid terminal WebSocket path')
    expect(FakeSocket.instances).toHaveLength(0)
    expect(h.calls('stop').map(req => req.body)).toEqual([{
      action: 'stop', sessionKey: 'native-own', sessionToken: 'session-secret-native-own', profile: 'default'
    }])
  })

  it('rejects nondefault profile and remote connection before any host operation', async () => {
    const h = harness()
    h.getProfile.mockReturnValue('customer-secondary')
    await expect(h.terminal.start()).rejects.toThrow('only the default profile')
    h.getProfile.mockReturnValue('default')
    h.getConnectionId.mockReturnValue('remote-connection')
    await expect(h.terminal.start()).rejects.toThrow('selected remote connection')
    expect(h.request).not.toHaveBeenCalled()
    expect(h.captureRequest).not.toHaveBeenCalled()
    h.getConnectionId.mockReturnValue('local')
    await h.start()
    expect(h.calls('start')).toHaveLength(1)
  })

  it('retains the actual server error rather than reporting success or losing it to shape validation', async () => {
    const h = harness(async () => ({ ok: false, error: 'Gateway container is stopped' }))
    await expect(h.terminal.start()).rejects.toThrow('Gateway container is stopped')
    expect(FakeSocket.instances).toHaveLength(0)
    expect(h.calls('stop')).toHaveLength(0)
  })

  it('cleans up a malformed successful start once it knows the session credentials', async () => {
    const h = harness(async request => (request.body as { action: string }).action === 'start'
      ? startReply('native-own', { shell: null }) : { ok: true })

    await expect(h.terminal.start()).rejects.toThrow('invalid terminal session details')
    expect(h.calls('stop')).toHaveLength(1)
  })

  it('does not stop a previous tab if a broken server returns its duplicate id', async () => {
    const h = harness(async request => (request.body as { action: string }).action === 'start' ? startReply() : { ok: true })
    const first = await h.start()
    await expect(h.terminal.start()).rejects.toThrow('duplicate terminal session')
    expect(h.calls('stop')).toHaveLength(0)
    await expect(h.terminal.write(first.session.id, 'still alive')).resolves.toBe(true)
  })

  it('replays bounded early output exactly once and honors data unsubscribe', async () => {
    const h = harness()
    const { session, socket } = await h.start()
    socket.message({ type: 'output', data: 'first\r\n' })
    socket.message({ type: 'output', data: 'second 🐚' })
    const first = vi.fn()
    const unsubscribe = h.terminal.onData(session.id, first)
    expect(first.mock.calls.flat()).toEqual(['first\r\n', 'second 🐚'])
    const second = vi.fn()
    const unsubscribeSecond = h.terminal.onData(session.id, second)
    expect(second).not.toHaveBeenCalled()
    socket.message({ type: 'output', data: 'live' })
    expect(first).toHaveBeenLastCalledWith('live')
    expect(second).toHaveBeenLastCalledWith('live')
    unsubscribe()
    socket.message({ type: 'output', data: 'only second' })
    expect(first).toHaveBeenCalledTimes(3)
    expect(second).toHaveBeenLastCalledWith('only second')
    unsubscribeSecond()
  })

  it('retains an exit before listener registration and cancels an unsubscribed replay', async () => {
    const h = harness()
    const pending = h.terminal.start()
    await flush()
    const socket = FakeSocket.instances[0]
    socket.open()
    socket.message({ type: 'output', data: 'last line' })
    socket.message({ type: 'closed', reason: 'exit', exitCode: 7, signal: 'SIGTERM', cleanupConfirmed: true })
    const session = await pending
    const output = vi.fn()
    h.terminal.onData(session.id, output)
    const cancelled = vi.fn()
    h.terminal.onExit(session.id, cancelled)()
    const onExit = vi.fn()
    h.terminal.onExit(session.id, onExit)
    await flush()
    expect(output).toHaveBeenCalledExactlyOnceWith('last line')
    expect(cancelled).not.toHaveBeenCalled()
    expect(onExit).toHaveBeenCalledExactlyOnceWith({ code: 7, signal: 'SIGTERM' })
    await expect(h.terminal.write(session.id, 'after exit')).resolves.toBe(false)
    await expect(h.terminal.dispose(session.id)).resolves.toBe(true)
    expect(h.calls('stop')).toHaveLength(0) // the server already confirmed the PTY exited
    expect(socket.close).toHaveBeenCalledOnce()
  })

  it('treats duplicate callback registrations as independently removable subscriptions', async () => {
    const h = harness()
    const { session, socket } = await h.start()
    const callback = vi.fn()
    const removeFirst = h.terminal.onData(session.id, callback)
    const removeSecond = h.terminal.onData(session.id, callback)
    socket.message({ type: 'output', data: 'one' })
    expect(callback).toHaveBeenCalledTimes(2)
    removeFirst()
    socket.message({ type: 'output', data: 'two' })
    expect(callback).toHaveBeenCalledTimes(3)
    removeSecond()
    socket.message({ type: 'output', data: 'three' })
    expect(callback).toHaveBeenCalledTimes(3)
    const exit = vi.fn()
    const removeExit = h.terminal.onExit(session.id, exit)
    h.terminal.onExit(session.id, exit)
    removeExit()
    socket.message({ type: 'closed', exitCode: 0, signal: null, cleanupConfirmed: true })
    expect(exit).toHaveBeenCalledExactlyOnceWith({ code: 0, signal: null })
  })

  it.each([false, undefined])('requires a real stop after a closed frame with cleanupConfirmed=%s', async cleanupConfirmed => {
    const h = harness(async request => (request.body as { action: string }).action === 'start' ? startReply() : { ok: false, error: 'Terminal cleanup could not be confirmed' })
    const { session, socket } = await h.start()
    const exit = vi.fn()
    h.terminal.onExit(session.id, exit)
    socket.message({ type: 'closed', reason: 'error', exitCode: null, signal: null, cleanupConfirmed })
    expect(exit).toHaveBeenCalledExactlyOnceWith({ code: null, signal: null })
    await expect(h.terminal.dispose(session.id)).resolves.toBe(false)
    expect(h.calls('stop')).toHaveLength(1)
    expect(h.calls('stop')[0].body).toMatchObject({ sessionKey: session.id, sessionToken: 'session-secret-native-1' })
  })

  it.each(['error', 'close'])('fails a %s during ticket attach, stops once, and never starts a replacement', async event => {
    const h = harness()
    const pending = h.terminal.start()
    const rejected = expect(pending).rejects.toThrow('Could not attach the terminal WebSocket')
    await flush()
    const socket = FakeSocket.instances[0]
    socket.dispatchEvent(new Event(event))
    await rejected
    expect(socket.close).toHaveBeenCalledOnce()
    expect(h.calls('stop')).toHaveLength(1)
    expect(h.calls('start')).toHaveLength(1)
    expect(h.calls('attach')).toHaveLength(0)
    expect(FakeSocket.instances).toHaveLength(1)
  })

  it('bounds a silent WebSocket handshake and cleans it up', async () => {
    const h = harness()
    const rejected = expect(h.terminal.start()).rejects.toThrow('connection timed out')
    await flush()
    await vi.advanceTimersByTimeAsync(10_000)
    await rejected
    expect(h.calls('stop')).toHaveLength(1)
    expect(FakeSocket.instances[0].close).toHaveBeenCalledOnce()
  })

  it('does not redial an expired ticket; the next explicit tab gets a new session and ticket', async () => {
    const h = harness()
    const rejected = expect(h.terminal.start()).rejects.toThrow('ticket may have expired')
    await flush()
    FakeSocket.instances[0].dispatchEvent(new CloseEvent('close', { code: 1008, reason: 'Expired terminal ticket' }))
    await rejected
    const second = await h.start()
    expect(second.session.id).toBe('native-2')
    expect(FakeSocket.instances.map(socket => new URL(socket.url).searchParams.get('token'))).toEqual(['ticket-native-1', 'ticket-native-2'])
    expect(h.calls('stop')).toHaveLength(1)
  })

  it('times out a lost start response but cleans up an eventual late response without opening a socket', async () => {
    const late = deferred<unknown>()
    const h = harness(async request => (request.body as { action: string }).action === 'start' ? late.promise : { ok: true })
    const rejected = expect(h.terminal.start()).rejects.toThrow('timed out')
    await vi.advanceTimersByTimeAsync(20_000)
    await rejected
    late.resolve(startReply('native-late'))
    await flush()
    expect(FakeSocket.instances).toHaveLength(0)
    expect(h.calls('stop')).toHaveLength(1)
    expect(h.calls('stop')[0].body).toMatchObject({ sessionKey: 'native-late', sessionToken: 'session-secret-native-late' })
  })

  it('stops a late start after page disposal and never reports it as open', async () => {
    const late = deferred<unknown>()
    const h = harness(async request => (request.body as { action: string }).action === 'start' ? late.promise : { ok: true })
    const rejected = expect(h.terminal.start()).rejects.toThrow('page closed')
    await flush()
    window.dispatchEvent(new Event('pagehide'))
    late.resolve(startReply())
    await rejected
    expect(FakeSocket.instances).toHaveLength(0)
    expect(h.calls('stop')[0].keepalive).toBe(true)
  })

  it.each(['pagehide', 'disconnect'])('does not report success when %s races the socket-open continuation', async event => {
    const h = harness()
    const rejected = expect(h.terminal.start()).rejects.toThrow(/cancelled|failed before it became ready/)
    await flush()
    const socket = FakeSocket.instances[0]
    socket.open()

    if (event === 'pagehide') {
      window.dispatchEvent(new Event('pagehide'))
    } else {
      socket.disconnect()
    }

    await rejected
    expect(h.calls('stop')).toHaveLength(1)
    expect(socket.close).toHaveBeenCalledOnce()
  })

  it('serializes concurrent writes, UTF-8 chunks and resize without interleaving', async () => {
    const held = deferred<unknown>()
    let inputCount = 0

    const h = harness(async request => {
      const body = request.body as { action: string }

      if (body.action === 'start') { return startReply() }

      if (body.action === 'input' && ++inputCount === 1) { return held.promise }

      return { ok: true }
    })

    const { session } = await h.start()
    const pasted = `${'🐚'.repeat(1023)}Aé${'漢'.repeat(1600)}`
    const first = h.terminal.write(session.id, pasted)
    const second = h.terminal.write(session.id, '\r')
    const resized = h.terminal.resize(session.id, { cols: 120, rows: 40 })
    await flush()
    expect(h.calls('input')).toHaveLength(1)
    expect(h.calls('resize')).toHaveLength(0)
    held.resolve({ ok: true })
    await expect(Promise.all([first, second, resized])).resolves.toEqual([true, true, true])
    const chunks = h.calls('input').map(request => (request.body as { data: string }).data)
    expect(chunks.join('')).toBe(pasted + '\r')
    expect(chunks.every(chunk => new TextEncoder().encode(chunk).byteLength <= 4096)).toBe(true)
    expect(h.request.mock.calls.at(-1)?.[0].body).toMatchObject({ action: 'resize', cols: 120, rows: 40 })
    expect(h.calls('input').every(request => (request.body as Record<string, unknown>).sessionToken === 'session-secret-native-1')).toBe(true)
  })

  it('disposal cancels queued input, closes the socket, and shares one actual stop request', async () => {
    const heldInput = deferred<unknown>()
    const heldStop = deferred<unknown>()

    const h = harness(async request => {
      const { action } = request.body as { action: string }

      return action === 'start' ? startReply() : action === 'input' ? heldInput.promise : heldStop.promise
    })

    const { session, socket } = await h.start()
    const onData = vi.fn()
    const onExit = vi.fn()
    h.terminal.onData(session.id, onData)
    h.terminal.onExit(session.id, onExit)
    const first = h.terminal.write(session.id, 'in-flight')
    await flush()
    const second = h.terminal.write(session.id, 'must not be sent')
    const stopped = h.terminal.dispose(session.id)
    const alsoStopped = h.terminal.dispose(session.id)
    await flush()
    socket.message({ type: 'output', data: 'late' })
    socket.disconnect()
    expect(onData).not.toHaveBeenCalled()
    expect(onExit).not.toHaveBeenCalled()
    expect(h.calls('stop')).toHaveLength(1)
    heldStop.resolve({ ok: true })
    heldInput.resolve({ ok: true })
    await expect(Promise.all([stopped, alsoStopped, first, second])).resolves.toEqual([true, true, false, false])
    expect(h.calls('input')).toHaveLength(1)
    expect(h.calls('input')[0].body).toMatchObject({ data: 'in-flight' })
    expect(socket.close).toHaveBeenCalledOnce()
    await expect(h.terminal.dispose(session.id)).resolves.toBe(false)
  })

  it('bounds control timeouts and never returns true for an uncertain write or stop', async () => {
    const h = harness(async request => (request.body as { action: string }).action === 'start' ? startReply() : new Promise(() => {}))
    const { session } = await h.start()
    const written = h.terminal.write(session.id, 'uncertain')
    await vi.advanceTimersByTimeAsync(10_000)
    await expect(written).resolves.toBe(false)
    const disposed = h.terminal.dispose(session.id)
    await vi.advanceTimersByTimeAsync(10_000)
    await expect(disposed).resolves.toBe(false)
    expect(h.calls('input')).toHaveLength(1)
    expect(h.calls('stop')).toHaveLength(1)
  })

  it('batches rapid typing behind a high-latency request without crossing resize boundaries', async () => {
    const firstAck = deferred<unknown>()
    const secondAck = deferred<unknown>()
    let inputCount = 0

    const h = harness(async request => {
      const action = (request.body as { action: string }).action

      if (action === 'start') { return startReply() }

      if (action === 'input' && ++inputCount === 1) { return firstAck.promise }

      if (action === 'input' && inputCount === 2) { return secondAck.promise }

      return { ok: true }
    })

    const { session } = await h.start()
    const writes = [h.terminal.write(session.id, 'p')]
    await flush()

    for (const key of 'wd && echo ready') {
      writes.push(h.terminal.write(session.id, key))
      await vi.advanceTimersByTimeAsync(40)
    }

    const resize = h.terminal.resize(session.id, { cols: 100, rows: 40 })
    writes.push(h.terminal.write(session.id, '\r'))
    expect(h.calls('input')).toHaveLength(1)
    firstAck.resolve({ ok: true })
    await flush()
    expect(h.calls('input').map(request => (request.body as { data: string }).data)).toEqual(['p', 'wd && echo ready'])
    expect(h.calls('resize')).toHaveLength(0)
    secondAck.resolve({ ok: true })
    await expect(Promise.all([...writes, resize])).resolves.toEqual(Array(writes.length + 1).fill(true))
    expect(h.request.mock.calls.slice(1).map(([request]) => (request.body as { action: string }).action)).toEqual(['input', 'input', 'resize', 'input'])
    expect(h.calls('input').at(-1)?.body).toMatchObject({ data: '\r' })
  })

  it('clamps transient narrow xterm columns to the server minimum for start and resize', async () => {
    const h = harness()
    const pending = h.terminal.start({ cols: 2, rows: 2 })
    await flush()
    FakeSocket.instances[0].open()
    const session = await pending
    await expect(h.terminal.resize(session.id, { cols: 5, rows: 3 })).resolves.toBe(true)
    expect(h.calls('start')[0].body).toMatchObject({ cols: 10, rows: 2 })
    expect(h.calls('resize')[0].body).toMatchObject({ cols: 10, rows: 3 })
    await expect(h.terminal.resize(session.id, { cols: NaN, rows: 3 })).resolves.toBe(false)
    expect(h.calls('resize')).toHaveLength(1)
  })

  it('tears down a disconnected tab without affecting another tab or resubscribing it', async () => {
    const h = harness()
    const one = await h.start()
    const two = await h.start()
    const output = vi.fn()
    const exited = vi.fn()
    h.terminal.onData(one.session.id, output)
    h.terminal.onExit(one.session.id, exited)
    one.socket.disconnect()
    await flush()
    expect(output).toHaveBeenCalledWith(expect.stringContaining('Terminal connection failed'))
    expect(exited).toHaveBeenCalledExactlyOnceWith({ code: null, signal: null })
    await expect(h.terminal.write(two.session.id, 'safe')).resolves.toBe(true)
    expect(h.calls('stop').map(request => (request.body as { sessionKey: string }).sessionKey)).toEqual([one.session.id])
    expect(FakeSocket.instances).toHaveLength(2)
  })

  it.each(['bytes', 'chunks'])('bounds early output by %s and closes the owned PTY on overflow', async mode => {
    const h = harness()
    const { session, socket } = await h.start()

    if (mode === 'bytes') {
      socket.message({ type: 'output', data: 'a'.repeat(256 * 1024) })
    } else {
      for (let i = 0; i < 256; i += 1) { socket.message({ type: 'output', data: 'a' }) }
    }

    socket.message({ type: 'output', data: 'overflow' })
    const output = vi.fn()
    h.terminal.onData(session.id, output)
    await flush()
    expect(output).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('buffer limit'))
    expect(h.calls('stop')).toHaveLength(1)
    await expect(h.terminal.write(session.id, 'not sent')).resolves.toBe(false)
  })

  it('bounds pasted input and pending operation count rather than buffering forever', async () => {
    const held = deferred<unknown>()
    const h = harness(async request => (request.body as { action: string }).action === 'start' ? startReply() : (request.body as { action: string }).action === 'stop' ? { ok: true } : held.promise)
    const { session } = await h.start()
    const writes = Array.from({ length: 129 }, () => h.terminal.write(session.id, 'a'))
    held.resolve({ ok: true })
    expect((await Promise.all(writes)).every(result => result === false)).toBe(true)
    expect(h.calls('input')).toHaveLength(0)
    expect(h.calls('stop')).toHaveLength(1)
    await h.terminal.dispose(session.id)
    const next = await h.start()
    await expect(h.terminal.write(next.session.id, '🐚'.repeat(20_000))).resolves.toBe(false)
    expect(h.calls('input')).toHaveLength(0)
  })

  it('returns only a fresh best-effort cwd, never the initial or prior value', async () => {
    let cwd: unknown = '/changed'
    const h = harness(async request => (request.body as { action: string }).action === 'start' ? startReply() : { ok: true, cwd })
    const { session } = await h.start()
    await expect(h.terminal.cwd(session.id)).resolves.toBe('/changed')
    cwd = null
    await expect(h.terminal.cwd(session.id)).resolves.toBeNull()
    cwd = 42
    await expect(h.terminal.cwd(session.id)).resolves.toBeNull()
    await expect(h.terminal.cwd('another-session')).resolves.toBeNull()
  })

  it('captures per-session transport and profile even after the active context changes', async () => {
    const h = harness()
    const { session } = await h.start()
    const otherRequest = vi.fn()
    h.captureRequest.mockImplementation(() => otherRequest)
    h.getProfile.mockReturnValue('other-profile')
    h.getConnectionId.mockReturnValue('other-host')
    await h.terminal.write(session.id, 'owned input')
    await h.terminal.resize(session.id, { cols: 90, rows: 30 })
    await h.terminal.cwd(session.id)
    await h.terminal.dispose(session.id)
    expect(otherRequest).not.toHaveBeenCalled()
    expect(h.captureRequest).toHaveBeenCalledOnce()
    expect(h.request.mock.calls.every(([request]) => (request.body as { profile: string }).profile === 'default')).toBe(true)
  })

  it('uses unique server sessions per tab, caps live tabs and cleans only its own ids on pagehide', async () => {
    const h = harness()
    const opened = []

    for (let i = 0; i < 4; i += 1) { opened.push(await h.start()) }
    expect(new Set(opened.map(({ session }) => session.id)).size).toBe(4)
    await expect(h.terminal.start()).rejects.toThrow('Close an existing terminal')
    await expect(h.terminal.write('not-owned', 'x')).resolves.toBe(false)
    await expect(h.terminal.resize('not-owned', { cols: 80, rows: 24 })).resolves.toBe(false)
    await expect(h.terminal.dispose('not-owned')).resolves.toBe(false)
    window.dispatchEvent(new Event('pagehide'))
    await flush()
    expect(h.calls('stop').map(request => (request.body as { sessionKey: string }).sessionKey).sort()).toEqual(opened.map(({ session }) => session.id).sort())
    expect(h.calls('stop').every(request => request.keepalive === true)).toBe(true)
    expect(opened.every(({ socket }) => socket.close.mock.calls.length === 1)).toBe(true)
  })

  it('ignores a broken subscriber without losing exit delivery or cleanup', async () => {
    const h = harness()
    const { session, socket } = await h.start()
    h.terminal.onData(session.id, () => { throw new Error('unmounted') })
    h.terminal.onExit(session.id, () => { throw new Error('unmounted') })
    const remaining = vi.fn()
    h.terminal.onExit(session.id, remaining)
    socket.disconnect()
    await flush()
    expect(remaining).toHaveBeenCalledOnce()
    expect(h.calls('stop')).toHaveLength(1)
  })
})

describe('web shim terminal integration', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.stubGlobal('hermesDesktop', undefined)
    vi.stubGlobal('__HERMES_BASE_PATH__', '/desktop')
    vi.stubGlobal('__HERMES_SESSION_TOKEN__', 'native-api-secret')
    sessionStorage.clear()
  })

  async function install(fetcher: (input: unknown, init?: RequestInit) => Promise<Response>) {
    vi.stubGlobal('fetch', vi.fn(fetcher))
    await import('./web-shim')

    return window.hermesDesktop.terminal
  }

  it('uses the existing authenticated API path, freezes auth/base per start and keeps API credentials off the socket URL', async () => {
    const terminal = await install(async (_input, init) => {
      const body = JSON.parse(String(init?.body))

      return Response.json(body.action === 'start' ? startReply() : { ok: true, cwd: null })
    })

    const pending = terminal.start({ cols: 90, rows: 26 })
    await flush()
    const socket = FakeSocket.instances[0]
    socket.open()
    const session = await pending
    vi.stubGlobal('__HERMES_BASE_PATH__', '/some-other-base')
    vi.stubGlobal('__HERMES_SESSION_TOKEN__', 'changed-secret')
    await terminal.write(session.id, 'pwd\r')
    await terminal.dispose(session.id)
    const calls = vi.mocked(fetch).mock.calls
    expect(calls).toHaveLength(3)

    for (const [url, init] of calls) {
      expect(url).toBe(`${window.location.origin}/desktop/api/desktop-terminal`)
      expect(init).toMatchObject({ method: 'POST', credentials: 'omit', redirect: 'error', headers: { Authorization: 'Bearer native-api-secret', 'Content-Type': 'application/json' } })
    }

    expect(socket.url).not.toContain('native-api-secret')
    expect(socket.url).not.toContain('session-secret')
    expect(calls[2][1]?.keepalive).toBe(true)
  })

  it.each([404, 405, 501, 200])('reports unsupported HTML server HTTP %s honestly instead of a JSON parse crash', async status => {
    const terminal = await install(async () => new Response('<html>Old server SPA</html>', { status }))
    await expect(terminal.start()).rejects.toThrow(/browser terminals.*support|support.*browser terminals/)
    expect(FakeSocket.instances).toHaveLength(0)
    expect(fetch).toHaveBeenCalledOnce()
  })

  it('retains a structured server denial and HTTP failures without mislabeling them successful', async () => {
    const terminal = await install(async () => Response.json({ error: 'Terminal request is not authenticated' }, { status: 401 }))
    await expect(terminal.start()).rejects.toThrow('Terminal request is not authenticated')
    expect(fetch).toHaveBeenCalledOnce()
  })

  it('retains a structured 404 from a capable server rather than claiming the capability is missing', async () => {
    const terminal = await install(async () => Response.json({ error: 'Managed gateway container not found' }, { status: 404 }))
    await expect(terminal.start()).rejects.toThrow('Managed gateway container not found')
  })

  it('refuses redirecting authenticated terminal requests instead of forwarding their POST body', async () => {
    const redirected = vi.fn()

    const terminal = await install(async (_input, init) => {
      if (init?.redirect === 'error') {
        throw new TypeError('fetch failed: unexpected redirect')
      }

      redirected(init?.body)

      return Response.json(startReply())
    })

    await expect(terminal.start()).rejects.toThrow('unexpected redirect')
    expect(redirected).not.toHaveBeenCalled()
    expect(fetch).toHaveBeenCalledOnce()
  })

  it('rejects malformed API-base configuration that would send credentials to another origin', async () => {
    vi.stubGlobal('__HERMES_BASE_PATH__', 'https://evil.example')
    const terminal = await install(async () => Response.json(startReply()))
    await expect(terminal.start()).rejects.toThrow('must stay on this server')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('aborts a stuck HTTP start at its deadline', async () => {
    let signal: AbortSignal | null | undefined

    const terminal = await install(async (_input, init) => {
      signal = init?.signal

      return new Promise((_resolve, reject) => signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))))
    })

    const rejected = expect(terminal.start()).rejects.toThrow(/timed out|Aborted/)
    await vi.advanceTimersByTimeAsync(20_000)
    await rejected
    expect(signal?.aborted).toBe(true)
    expect(fetch).toHaveBeenCalledOnce()
  })

  it('leaves an existing Electron bridge untouched', async () => {
    const nativeTerminal = { start: vi.fn() }
    const nativeBridge = { terminal: nativeTerminal }
    vi.stubGlobal('hermesDesktop', nativeBridge)
    const fetcher = vi.fn()
    await install(fetcher)
    expect(window.hermesDesktop).toBe(nativeBridge)
    expect(window.hermesDesktop.terminal).toBe(nativeTerminal)
    expect(fetcher).not.toHaveBeenCalled()
    expect(FakeSocket.instances).toHaveLength(0)
  })
})
