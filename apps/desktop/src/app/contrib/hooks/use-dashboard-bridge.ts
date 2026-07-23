import { useEffect, useRef } from 'react'

/**
 * hermes-fork: Dashboard → iframe bridge.
 *
 * When this chat runs inside the HermesOS dashboard's cross-origin iframe,
 * accept a starter prompt the parent posts and send it as a user message —
 * exactly as if the user typed it. This powers the dashboard welcome
 * starter-prompt strip: clicking a suggestion creates the first backend
 * session (submitText calls createBackendSessionForSend when there is no
 * active session, which stamps first_usage) without the user having to type
 * into an unfamiliar embedded chat. submitText surfaces its own errors, so
 * this stays a thin, validated forwarder. Guards mirror the appearance
 * listener in themes/context.tsx: only when actually iframed, only from
 * window.parent.
 *
 * (Ported from the retired desktop-controller.tsx when upstream moved to the
 * contribution shell.)
 */

// Parallels the appearance message in themes/context.tsx.
const DASHBOARD_SEND_MESSAGE_TYPE = 'hermes-dashboard:send-message'

export function useDashboardBridge({ submitText }: { submitText: (text: string) => Promise<unknown> | unknown }): void {
  // Register once; track the latest callback through a ref so re-renders never
  // leave a listener gap (same pattern as use-pet-bridge).
  const submitTextRef = useRef(submitText)
  submitTextRef.current = submitText

  useEffect(() => {
    if (typeof window === 'undefined' || window === window.parent) {
      return
    }

    const onMessage = (event: MessageEvent) => {
      if (event.source !== window.parent) {return}

      const data = event.data as { type?: unknown; source?: unknown; text?: unknown } | null | undefined

      if (
        !data ||
        typeof data !== 'object' ||
        data.type !== DASHBOARD_SEND_MESSAGE_TYPE ||
        data.source !== 'hermes-dashboard' ||
        typeof data.text !== 'string'
      ) {
        return
      }

      const text = data.text.trim()

      if (!text) {return}

      void submitTextRef.current(text)
    }

    window.addEventListener('message', onMessage)

    return () => window.removeEventListener('message', onMessage)
  }, [])
}
