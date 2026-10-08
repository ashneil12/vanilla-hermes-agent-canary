import { type CSSProperties, type ReactNode, useRef } from 'react'

// Off-screen (NOT display:none) so a programmatic input.click() reliably opens
// the native file dialog; some browsers won't open a chooser for display:none.
const OFFSCREEN_INPUT_STYLE: CSSProperties = {
  position: 'fixed',
  left: '-9999px',
  top: '-9999px',
  opacity: 0,
  pointerEvents: 'none'
}

export interface WebFilePicker {
  /** True only on the hosted web client with an attach handler wired. */
  enabled: boolean
  /** Real DOM onClick handlers: they keep the click's transient user activation. */
  pickFiles: () => void
  pickImages: () => void
  /** Persistent hidden inputs; render OUTSIDE the dropdown so they outlive its close. */
  inputs: ReactNode
}

/**
 * Hosted-web file pickers for the composer "+" menu.
 *
 * The Files / Images rows cannot go through Radix's `onSelect` ->
 * `selectPaths` -> `input.click()` chain: `onSelect` fires inside Radix's
 * synthetic event dispatch, and in the cross-origin dashboard iframe that
 * boundary does not carry transient user activation, so Chrome silently
 * declines to open the native chooser (no dialog, no error). Paste and drag
 * never open a chooser, so they are unaffected. Fix: click a persistent hidden
 * <input> from a REAL DOM `onClick`, then route the chosen File[] through the
 * same path drag-drop uses (`onAttachDroppedItems` -> `getPathForFile`).
 *
 * Native (Electron) keeps its IPC picker: `enabled` is false there.
 */
export function useWebFilePicker(onAttach?: (files: File[]) => void): WebFilePicker {
  const filesRef = useRef<HTMLInputElement>(null)
  const imagesRef = useRef<HTMLInputElement>(null)

  const enabled =
    typeof window !== 'undefined' &&
    Boolean((window as unknown as { __HERMES_WEB_CLIENT__?: boolean }).__HERMES_WEB_CLIENT__) &&
    Boolean(onAttach)

  const drain = (input: HTMLInputElement | null) => {
    if (!input || !onAttach) {
      return
    }

    const files = Array.from(input.files ?? [])

    input.value = '' // reset so re-picking the same file fires change again

    if (files.length) {
      onAttach(files)
    }
  }

  return {
    enabled,
    pickFiles: () => filesRef.current?.click(),
    pickImages: () => imagesRef.current?.click(),
    inputs: enabled ? (
      <>
        <input
          multiple
          onChange={() => drain(filesRef.current)}
          ref={filesRef}
          style={OFFSCREEN_INPUT_STYLE}
          tabIndex={-1}
          type="file"
        />
        <input
          accept="image/*"
          multiple
          onChange={() => drain(imagesRef.current)}
          ref={imagesRef}
          style={OFFSCREEN_INPUT_STYLE}
          tabIndex={-1}
          type="file"
        />
      </>
    ) : null
  }
}
