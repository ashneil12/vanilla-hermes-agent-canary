/**
 * Hosted-web file bridge.
 *
 * A browser has no local filesystem path for a picked / dropped / pasted File,
 * and Desktop's remote-gateway attach flow is path based: the composer chip
 * keeps a `path`, and at send time `uploadComposerAttachment` (remote mode)
 * reads the bytes back through `hermesDesktop.readFileDataUrl*` and ships them
 * to the gateway with `file.attach` / `image.attach_bytes`, which stage them
 * server side. So the web shim only has to hand the renderer a stable
 * SYNTHETIC path per File and serve its bytes on demand. No bespoke upload
 * endpoint is needed (the retired `/api/attachments/upload`).
 *
 * Synthetic paths never exist on the gateway, so `file.attach` always falls
 * through to its `data_url` branch (tui_gateway/prompt_attachments.py).
 */

export const WEB_FILE_ROOT = '/hermes-web-upload'

// Raw-bytes cap. The gateway accepts WebSocket frames up to
// `_DESKTOP_ATTACHMENT_WS_MAX_BYTES` (384 MiB, hermes_cli/web_server_chat.py);
// base64 inflates by a third and the renderer holds the whole file in memory.
export const WEB_ATTACH_MAX_BYTES = 50 * 1024 * 1024

const filesByPath = new Map<string, Blob>()
const pathsByFile = new WeakMap<Blob, string>()
let sequence = 0

export interface WebSelectPathsOptions {
  title?: string
  defaultPath?: string
  directories?: boolean
  multiple?: boolean
  filters?: Array<{ name: string; extensions: string[] }>
}

export function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.addEventListener('load', () => {
      if (typeof reader.result === 'string') {
        resolve(reader.result)
      } else {
        reject(new Error('Could not read file'))
      }
    })
    reader.addEventListener('error', () => reject(reader.error || new Error('Could not read file')))
    reader.readAsDataURL(blob)
  })
}

/** Stable synthetic path for a File/Blob (same object -> same path). */
export function registerWebFile(blob: Blob, name?: string): string {
  const existing = pathsByFile.get(blob)

  if (existing) {
    return existing
  }

  const rawName = name || (blob as File).name || 'upload'

  // The basename is what the composer chip shows; keep it readable but never a path.
  // Path separators and control characters can never be part of the basename.
  const cleaned = [...rawName]
    .map(char => (char === '/' || char === '\\' || char < ' ' ? '_' : char))
    .join('')
    .trim()

  const safeName = !cleaned || cleaned === '.' || cleaned === '..' ? 'upload' : cleaned
  const path = `${WEB_FILE_ROOT}/${Date.now().toString(36)}-${(sequence++).toString(36)}/${safeName}`

  filesByPath.set(path, blob)
  pathsByFile.set(blob, path)

  return path
}

export function isWebFilePath(path: string): boolean {
  return filesByPath.has(path)
}

/**
 * Bytes of a registered file as a data URL; '' for any other path.
 *
 * Over-cap files reject with the same "file is too large (N bytes; limit M
 * bytes)" shape Electron's IPC uses, so `friendlyRemoteAttachError` renders
 * the usual "too large to upload to the remote gateway" message.
 */
export async function readWebFileDataUrl(path: string): Promise<string> {
  const blob = filesByPath.get(path)

  if (!blob) {
    return ''
  }

  if (blob.size > WEB_ATTACH_MAX_BYTES) {
    throw new Error(`file is too large (${blob.size} bytes; limit ${WEB_ATTACH_MAX_BYTES} bytes)`)
  }

  return blobToDataUrl(blob)
}

export function imageMimeForExtension(ext: string): string {
  switch (ext.replace(/^\./, '').toLowerCase()) {
    case 'bmp':
      return 'image/bmp'

    case 'gif':
      return 'image/gif'

    case 'jpg':

    case 'jpeg':
      return 'image/jpeg'

    case 'svg':
      return 'image/svg+xml'

    case 'tif':

    case 'tiff':
      return 'image/tiff'

    case 'webp':
      return 'image/webp'

    case 'ico':
      return 'image/x-icon'

    default:
      return 'image/png'
  }
}

function acceptFromFilters(filters?: WebSelectPathsOptions['filters']): string {
  const exts = new Set<string>()

  for (const filter of filters ?? []) {
    for (const ext of filter.extensions ?? []) {
      const clean = ext.trim().replace(/^\.+/, '')

      if (clean) {
        exts.add(`.${clean}`)
      }
    }
  }

  return [...exts].join(',')
}

/** `selectPaths` for the browser: native picker -> synthetic paths. */
export function selectBrowserFiles(options: WebSelectPathsOptions = {}): Promise<string[]> {
  if (options.directories || typeof document === 'undefined' || !document.body) {
    return Promise.resolve([])
  }

  return new Promise(resolve => {
    const input = document.createElement('input')
    input.type = 'file'
    input.multiple = options.multiple !== false
    input.style.position = 'fixed'
    input.style.left = '-9999px'
    input.style.top = '-9999px'
    input.style.opacity = '0'
    input.style.pointerEvents = 'none'

    const accept = acceptFromFilters(options.filters)

    if (accept) {
      input.accept = accept
    }

    let settled = false
    let dialogOpened = false

    const cleanup = () => {
      input.removeEventListener('change', onChange)
      input.removeEventListener('cancel', onCancel)
      window.removeEventListener('focus', onWindowFocus)
      window.removeEventListener('blur', onWindowBlur)
      input.remove()
    }

    const settle = (paths: string[]) => {
      if (settled) {
        return
      }

      settled = true
      cleanup()
      resolve(paths)
    }

    // Opening the native file dialog blurs the window; only a focus AFTER that
    // blur means "dialog dismissed". Without the gate a spurious focus (the
    // attach dropdown closing) tore the input down before the dialog opened.
    const onWindowBlur = () => {
      dialogOpened = true
    }

    const onWindowFocus = () => {
      if (!dialogOpened) {
        return
      }

      // macOS commits the selection slightly AFTER focus returns, so give
      // `change` a generous grace; `cancel` handles fast cancellation.
      window.setTimeout(() => {
        if (!settled && (!input.files || input.files.length === 0)) {
          settle([])
        }
      }, 1000)
    }

    function onChange() {
      settle(Array.from(input.files ?? []).map(file => registerWebFile(file)))
    }

    function onCancel() {
      settle([])
    }

    input.addEventListener('change', onChange)
    input.addEventListener('cancel', onCancel)
    window.addEventListener('blur', onWindowBlur)
    window.addEventListener('focus', onWindowFocus)

    document.body.appendChild(input)

    try {
      input.click()
    } catch (err) {
      console.error('Hermes web file picker failed', err)
      settle([])
    }
  })
}
