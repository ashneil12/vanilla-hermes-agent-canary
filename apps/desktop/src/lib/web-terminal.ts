import type { HermesTerminalExit, HermesTerminalSession } from '@/global'

interface TerminalRequest {
  path: string
  method: string
  body: unknown
  timeoutMs: number
  keepalive?: boolean
}

type TerminalTransport = <T>(request: TerminalRequest) => Promise<T>

interface WebTerminalOptions {
  captureRequest: () => TerminalTransport
  getProfile: () => string | null
  getConnectionId: () => string | null
}

interface SessionIdentity {
  sessionKey: string
  sessionToken: string
  profile: string
  request: TerminalTransport
}

interface InputBatch {
  parts: string[]
  result: Promise<boolean>
}

interface Session extends SessionIdentity {
  dataListeners: Set<(data: string) => void>
  exitListeners: Set<(exit: HermesTerminalExit) => void>
  output: string[]
  outputBytes: number
  exit: HermesTerminalExit | null
  serverClosed: boolean
  cleanupConfirmed: boolean
  disposed: boolean
  disconnect: (() => void) | null
  rejectStart: ((error: Error) => void) | null
  stop: Promise<boolean> | null
  queue: Promise<unknown>
  queuedBytes: number
  queuedOperations: number
  pendingInput: InputBatch | null
}

const API_PATH = '/api/desktop-terminal'
const START_TIMEOUT_MS = 20_000
const CONNECT_TIMEOUT_MS = 10_000
const CONTROL_TIMEOUT_MS = 10_000
const MAX_SESSIONS = 4
const MAX_INPUT_BYTES = 4096
const MAX_QUEUED_BYTES = 64 * 1024
const MAX_QUEUED_OPERATIONS = 128
const MAX_OUTPUT_BYTES = 256 * 1024
const MAX_OUTPUT_CHUNKS = 256
const encoder = new TextEncoder()

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function checkedReply(value: unknown): Record<string, unknown> {
  if (!isRecord(value) || value.ok !== true) {
    throw new Error(
      isRecord(value) && typeof value.error === 'string'
        ? value.error
        : 'The server did not confirm the terminal operation'
    )
  }

  return value
}

function identity(value: unknown, profile: string, request: TerminalTransport): SessionIdentity | null {
  if (
    !isRecord(value) ||
    typeof value.sessionKey !== 'string' ||
    !/^[a-zA-Z0-9:_-]{1,256}$/.test(value.sessionKey) ||
    typeof value.sessionToken !== 'string' ||
    !value.sessionToken ||
    value.sessionToken.length > 4096
  ) {
    return null
  }

  return { sessionKey: value.sessionKey, sessionToken: value.sessionToken, profile, request }
}

function socketUrl(path: unknown): string {
  const origin = new URL(window.location.origin)

  if (
    !['http:', 'https:'].includes(origin.protocol) ||
    typeof path !== 'string' ||
    path.length > 8192 ||
    !/^\/_sidecar\/api\/terminal\/ws\?[^#\\\s]+$/.test(path)
  ) {
    throw new Error('The server returned an invalid terminal WebSocket path')
  }

  const url = new URL(path, origin)
  const params = url.searchParams

  if (
    url.origin !== origin.origin ||
    url.pathname !== '/_sidecar/api/terminal/ws' ||
    url.username ||
    url.password ||
    url.hash ||
    params.getAll('token').length !== 1 ||
    !params.get('token') ||
    params.getAll('includeScrollback').length > 1 ||
    (params.has('includeScrollback') && params.get('includeScrollback') !== '1') ||
    [...params.keys()].some(key => key !== 'token' && key !== 'includeScrollback')
  ) {
    throw new Error('The server returned an invalid terminal WebSocket path')
  }

  url.protocol = origin.protocol === 'https:' ? 'wss:' : 'ws:'

  return url.toString()
}

function dimensions(cols = 80, rows = 24): { cols: number; rows: number } {
  if (!Number.isInteger(cols) || !Number.isInteger(rows) || cols < 2 || rows < 2 || cols > 500 || rows > 200) {
    throw new Error('Invalid terminal dimensions')
  }

  // xterm may briefly fit a narrow/hidden pane below the PTY's minimum width.
  return { cols: Math.max(10, cols), rows }
}

function inputChunks(data: string): string[] {
  const chunks: string[] = []
  let chunk = ''
  let bytes = 0

  // Iterate code points, not UTF-16 units: a paste must not split an emoji or
  // exceed the server's UTF-8 byte limit even when every character is wide.
  for (const character of data) {
    const size = encoder.encode(character).byteLength

    if (bytes + size > MAX_INPUT_BYTES) {
      chunks.push(chunk)
      chunk = ''
      bytes = 0
    }

    chunk += character
    bytes += size
  }

  if (chunk) {
    chunks.push(chunk)
  }

  return chunks
}

/** Browser implementation of the existing, narrow Electron PTY capability.
 * Credentials stay in this closure; a renderer tab only receives its own id.
 * There is deliberately no automatic reconnect/start retry: a failed dial may
 * already own a PTY, so recovery must close that session before starting anew.
 */
export function createWebTerminal(options: WebTerminalOptions): Window['hermesDesktop']['terminal'] {
  const sessions = new Map<string, Session>()
  let pendingStarts = 0
  let pageGeneration = 0
  let watchingPage = false

  function watchPage() {
    if (!watchingPage) {
      window.addEventListener('pagehide', onPageHide)
      watchingPage = true
    }
  }

  function unwatchPage() {
    if (watchingPage && !pendingStarts && !sessions.size) {
      window.removeEventListener('pagehide', onPageHide)
      watchingPage = false
    }
  }

  function post(request: TerminalTransport, body: Record<string, unknown>, deadline: number, onLate?: (value: unknown) => void): Promise<unknown> {
    const timeoutMs = deadline - Date.now()

    if (timeoutMs <= 0) {
      return Promise.reject(new Error('Terminal operation timed out'))
    }

    // fetchJson aborts the HTTP request too. The outer deadline also bounds a
    // delayed transport/body reader; late start replies still get scoped cleanup.
    return new Promise((resolve, reject) => {
      let settled = false

      const timer = window.setTimeout(() => {
        settled = true
        reject(new Error('Terminal operation timed out'))
      }, timeoutMs)

      Promise.resolve()
        .then(() => request<unknown>({
          path: API_PATH,
          method: 'POST',
          body,
          timeoutMs,
          ...(body.action === 'stop' ? { keepalive: true } : {})
        }))
        .then(value => {
          if (settled) {
            onLate?.(value)

            return
          }

          settled = true
          window.clearTimeout(timer)
          resolve(value)
        }, error => {
          if (!settled) {
            settled = true
            window.clearTimeout(timer)
            reject(error)
          }
        })
    })
  }

  function control(session: SessionIdentity, action: string, fields: Record<string, unknown> = {}, deadline = Date.now() + CONTROL_TIMEOUT_MS) {
    return post(session.request, { ...fields, action, sessionKey: session.sessionKey, sessionToken: session.sessionToken, profile: session.profile }, deadline)
      .then(checkedReply)
  }

  function stop(session: Session): Promise<boolean> {
    if (session.cleanupConfirmed) {
      return Promise.resolve(true)
    }

    session.stop ??= control(session, 'stop').then(() => true, () => false)

    return session.stop
  }

  function cleanupLateStart(value: unknown, profile: string, request: TerminalTransport) {
    const owned = identity(value, profile, request)

    if (owned && !sessions.has(owned.sessionKey)) {
      // No blind retries if the HTTP outcome is uncertain. Native sessions also
      // have server-side unattached/disconnected expiry for a lost response.
      void control(owned, 'stop').catch(() => {})
    }
  }

  function notify<T>(listeners: Set<(value: T) => void>, value: T) {
    for (const listener of [...listeners]) {
      if (listeners.has(listener)) {
        try {
          listener(value)
        } catch {
          // One unmounted/broken subscriber must not prevent PTY cleanup or
          // delivery to another subscriber. Never log terminal output/tickets.
        }
      }
    }
  }

  function finish(session: Session, exit: HermesTerminalExit, error?: string) {
    if (session.exit || session.disposed) {
      return
    }

    session.exit = exit

    if (error) {
      const message = `\r\n${error}\r\n`

      if (session.dataListeners.size) {
        notify(session.dataListeners, message)
      } else {
        session.output = [message]
        session.outputBytes = encoder.encode(message).byteLength
      }
    }

    session.rejectStart?.(new Error(error || 'Terminal closed before it connected'))
    session.disconnect?.()
    notify(session.exitListeners, exit)
  }

  function fail(session: Session, message: string) {
    finish(session, { code: null, signal: null }, message)
    void stop(session)
  }

  function output(session: Session, data: string) {
    if (session.dataListeners.size) {
      notify(session.dataListeners, data)

      return
    }

    const size = encoder.encode(data).byteLength

    if (session.output.length >= MAX_OUTPUT_CHUNKS || session.outputBytes + size > MAX_OUTPUT_BYTES) {
      fail(session, 'Terminal output exceeded its buffer limit; open a new terminal to continue')

      return
    }

    session.output.push(data)
    session.outputBytes += size
  }

  function connect(session: Session, path: unknown): Promise<void> {
    return new Promise((resolve, reject) => {
      const socket = new WebSocket(socketUrl(path))
      let connected = false
      const timer = window.setTimeout(() => fail(session, 'Terminal WebSocket connection timed out'), CONNECT_TIMEOUT_MS)

      session.rejectStart = reject

      session.disconnect = () => {
        window.clearTimeout(timer)
        socket.removeEventListener('open', onOpen)
        socket.removeEventListener('message', onMessage)
        socket.removeEventListener('error', onError)
        socket.removeEventListener('close', onClose)
        session.disconnect = null
        session.rejectStart = null

        try {
          socket.close()
        } catch {
          // HTTP stop and server-side disconnect expiry still own cleanup.
        }
      }

      function onOpen() {
        connected = true
        window.clearTimeout(timer)
        session.rejectStart = null
        resolve()
      }

      function onMessage(event: MessageEvent) {
        if (session.disposed || session.exit) {
          return
        }

        try {
          if (typeof event.data !== 'string' || event.data.length > MAX_OUTPUT_BYTES * 6 + 1024) {
            throw new Error('Invalid terminal frame')
          }

          const message: unknown = JSON.parse(event.data)

          if (!isRecord(message)) {
            throw new Error('Invalid terminal frame')
          }

          if (message.type === 'output' && typeof message.data === 'string' && encoder.encode(message.data).byteLength <= MAX_OUTPUT_BYTES) {
            output(session, message.data)
          } else if (message.type === 'closed') {
            if (
              !(message.exitCode === null || (typeof message.exitCode === 'number' && Number.isInteger(message.exitCode))) ||
              !(message.signal === null || (typeof message.signal === 'string' && message.signal.length <= 64))
            ) {
              throw new Error('Invalid terminal exit')
            }

            session.serverClosed = true
            session.cleanupConfirmed = message.cleanupConfirmed === true
            finish(session, { code: message.exitCode as number | null, signal: message.signal as string | null })
          } else if (message.type !== 'pong') {
            throw new Error('Invalid terminal frame')
          }
        } catch {
          fail(session, 'Terminal received an invalid server message')
        }
      }

      function onError() {
        fail(session, connected ? 'Terminal connection failed; open a new terminal to continue' : 'Could not attach the terminal WebSocket (the ticket may have expired)')
      }

      function onClose() {
        onError()
      }

      socket.addEventListener('open', onOpen)
      socket.addEventListener('message', onMessage)
      socket.addEventListener('error', onError)
      socket.addEventListener('close', onClose)
    })
  }

  function reserveInput(session: Session, bytes: number): boolean {
    if (session.disposed || session.exit) {
      return false
    }

    if (session.queuedBytes + bytes > MAX_QUEUED_BYTES || session.queuedOperations >= MAX_QUEUED_OPERATIONS) {
      fail(session, 'Terminal input exceeded its queue limit; open a new terminal to continue')

      return false
    }

    session.queuedBytes += bytes
    session.queuedOperations += 1

    return true
  }

  function releaseInput(session: Session, bytes: number) {
    session.queuedBytes -= bytes
    session.queuedOperations -= 1
  }

  function enqueue(session: Session, bytes: number, work: (deadline: number) => Promise<void>): Promise<boolean> {
    if (!reserveInput(session, bytes)) {
      return Promise.resolve(false)
    }

    const deadline = Date.now() + CONTROL_TIMEOUT_MS

    const result = session.queue.then(async () => {
      if (session.disposed || session.exit) {
        return false
      }

      try {
        await work(deadline)

        return !session.disposed && !session.exit
      } catch {
        fail(session, 'Terminal control failed; open a new terminal to continue')

        return false
      }
    }).finally(() => releaseInput(session, bytes))

    session.queue = result

    return result
  }

  async function dispose(id: string): Promise<boolean> {
    const session = sessions.get(id)

    if (!session) {
      return false
    }

    session.disposed = true
    session.dataListeners.clear()
    session.exitListeners.clear()
    session.output = []
    session.outputBytes = 0
    session.pendingInput = null
    session.rejectStart?.(new Error('Terminal was disposed before it connected'))
    session.disconnect?.()
    const stopped = await stop(session)
    sessions.delete(id)
    unwatchPage()

    return stopped
  }

  function onPageHide() {
    pageGeneration += 1

    for (const id of sessions.keys()) {
      void dispose(id)
    }
  }

  return {
    async start(settings = {}): Promise<HermesTerminalSession> {
      const profile = options.getProfile() || 'default'
      const connection = options.getConnectionId()

      if (connection && connection !== 'local') {
        throw new Error('Browser terminals are not available for the selected remote connection')
      }

      if (profile !== 'default') {
        throw new Error('Browser terminals currently support only the default profile')
      }

      const size = dimensions(settings.cols, settings.rows)

      if (settings.cwd !== undefined && (typeof settings.cwd !== 'string' || settings.cwd.length > 4096 || settings.cwd.includes('\0'))) {
        throw new Error('Invalid terminal working directory')
      }

      if (pendingStarts + sessions.size >= MAX_SESSIONS) {
        throw new Error('Close an existing terminal before opening another')
      }

      const request = options.captureRequest()
      pendingStarts += 1
      watchPage()
      const generation = pageGeneration
      let awaitingReply = true
      let session: Session | undefined
      let response: unknown

      try {
        response = await post(request, { action: 'start', ...size, ...(settings.cwd !== undefined ? { cwd: settings.cwd } : {}), profile }, Date.now() + START_TIMEOUT_MS, value => cleanupLateStart(value, profile, request))
        pendingStarts -= 1
        awaitingReply = false
        const owned = identity(response, profile, request)

        if (!owned) {
          checkedReply(response)
          throw new Error('The server returned invalid terminal session credentials')
        }

        if (sessions.has(owned.sessionKey)) {
          throw new Error('The server returned an invalid or duplicate terminal session')
        }

        session = { ...owned, dataListeners: new Set(), exitListeners: new Set(), output: [], outputBytes: 0, exit: null, serverClosed: false, cleanupConfirmed: false, disposed: false, disconnect: null, rejectStart: null, stop: null, queue: Promise.resolve(), queuedBytes: 0, queuedOperations: 0, pendingInput: null }
        sessions.set(owned.sessionKey, session)
        const reply = checkedReply(response)

        if (typeof reply.cwd !== 'string' || reply.cwd.length > 4096 || typeof reply.shell !== 'string' || !reply.shell || reply.shell.length > 128) {
          throw new Error('The server returned invalid terminal session details')
        }

        if (generation !== pageGeneration) {
          throw new Error('Terminal start was cancelled when the page closed')
        }

        await connect(session, reply.webSocketPath)

        if (session.disposed || generation !== pageGeneration) {
          throw new Error('Terminal start was cancelled when the page closed')
        }

        if (session.exit && !session.serverClosed) {
          throw new Error('Terminal connection failed before it became ready')
        }

        return { id: session.sessionKey, cwd: reply.cwd, shell: reply.shell }
      } catch (error) {
        if (session) {
          await dispose(session.sessionKey)
        } else {
          cleanupLateStart(response, profile, request)
        }

        throw error
      } finally {
        if (awaitingReply) {
          pendingStarts -= 1
        }

        unwatchPage()
      }
    },
    dispose,
    async cwd(id) {
      const session = sessions.get(id)

      if (!session || session.disposed || session.exit) {
        return null
      }

      try {
        const reply = await control(session, 'cwd')

        return !session.disposed && !session.exit && typeof reply.cwd === 'string' && reply.cwd ? reply.cwd : null
      } catch {
        return null
      }
    },
    resize(id, size) {
      const session = sessions.get(id)

      if (!session) {
        return Promise.resolve(false)
      }

      try {
        const checked = dimensions(size.cols, size.rows)
        // A resize is an ordering boundary: later input cannot join a batch
        // queued before this resize.
        session.pendingInput = null

        return enqueue(session, 0, async deadline => { await control(session, 'resize', checked, deadline) })
      } catch {
        return Promise.resolve(false)
      }
    },
    write(id, data) {
      const session = sessions.get(id)

      if (!session || typeof data !== 'string') {
        return Promise.resolve(false)
      }

      const bytes = data.length <= MAX_QUEUED_BYTES ? encoder.encode(data).byteLength : MAX_QUEUED_BYTES + 1

      if (!bytes) {
        return Promise.resolve(!session.disposed && !session.exit)
      }

      if (session.pendingInput) {
        if (!reserveInput(session, bytes)) {
          return Promise.resolve(false)
        }

        session.pendingInput.parts.push(data)

        return session.pendingInput.result.finally(() => releaseInput(session, bytes))
      }

      // Batch keystrokes that arrive while an earlier HTTP control is in flight.
      // This keeps high-RTT typing to one bounded request per batch, not one RTT
      // per character. Adjacent writes share acknowledgement, never a retry.
      const batch: InputBatch = { parts: [data], result: Promise.resolve(false) }
      batch.result = enqueue(session, bytes, async deadline => {
        if (session.pendingInput === batch) {
          session.pendingInput = null
        }

        for (const chunk of inputChunks(batch.parts.join(''))) {
          if (session.disposed || session.exit) {
            return
          }

          await control(session, 'input', { data: chunk }, deadline)
        }
      })

      if (!session.disposed && !session.exit) {
        session.pendingInput = batch
      }

      return batch.result
    },
    onData(id, callback) {
      const session = sessions.get(id)

      if (!session || session.disposed) {
        return () => {}
      }

      const listener = (data: string) => callback(data)
      session.dataListeners.add(listener)
      const buffered = session.output
      session.output = []
      session.outputBytes = 0

      for (const data of buffered) {
        if (session.dataListeners.has(listener)) {
          notify(new Set([listener]), data)
        }
      }

      return () => { session.dataListeners.delete(listener) }
    },
    onExit(id, callback) {
      const session = sessions.get(id)

      if (!session || session.disposed) {
        return () => {}
      }

      const listener = (exit: HermesTerminalExit) => callback(exit)
      session.exitListeners.add(listener)

      if (session.exit) {
        const exit = session.exit
        queueMicrotask(() => {
          if (session.exitListeners.has(listener)) {
            notify(new Set([listener]), exit)
          }
        })
      }

      return () => { session.exitListeners.delete(listener) }
    }
  }
}
