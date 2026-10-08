import { useEffect, useState } from 'react'

import { Codicon } from '@/components/ui/codicon'
import { hermesApi } from '@/hermes'
import { openExternalLink } from '@/lib/external-link'
import { ChevronRight } from '@/lib/icons'

// The recommended way to run a managed Hivra agent. Venice isn't an OAuth
// provider: it's the managed service Hivra runs for you (server-side proxy key,
// billed to your dashboard wallet). Enabling it is a dashboard flow (Clerk +
// wallet), not an in-app browser sign-in, so this card deep-links there. The
// dashboard origin comes from the fork-only `GET /api/hivra/config`
// (`dashboard_url`, from HERMES_DASHBOARD_URL; hermes_cli/web_routers/fork_hivra.py).
// If it's missing (e.g. local dev, or a backend without that route) the card
// falls back to the API-key path so it is never a dead end.
// hermes-fork: venice-card. Do not put the words "API key" in this button's text: upstream's
// onboarding e2e (e2e/core/onboarding-first-chat.spec.ts) expects exactly ONE button matching /api key/i.
const MANAGED_VENICE_PITCH = 'Managed by Hivra — private frontier models, nothing to copy or paste'

const managedVeniceEnableUrl = (dashboardUrl: string) =>
  `${dashboardUrl.replace(/\/+$/, '')}/dashboard/billing?managedVenice=deposit&wallet=hermesos`

export function VeniceRecommendedCard({ onWantApiKey }: { onWantApiKey: () => void }) {
  // Fetched directly (no react-query) so the card renders in any context,
  // including unit tests that mount without a QueryClientProvider. The
  // try/catch also absorbs a synchronous throw when the bridge isn't installed.
  const [dashboardUrl, setDashboardUrl] = useState<null | string>(null)

  useEffect(() => {
    let cancelled = false

    void (async () => {
      try {
        const config = await hermesApi<{ dashboard_url?: null | string }>({ path: '/api/hivra/config' })

        if (!cancelled) {
          setDashboardUrl(config?.dashboard_url ?? null)
        }
      } catch {
        /* config unavailable: leave null, the click falls back to the API-key path */
      }
    })()

    return () => {
      cancelled = true
    }
  }, [])

  return (
    <button
      className="group relative flex w-full items-center justify-between gap-4 rounded-[8px] bg-primary/[0.06] px-3 py-2.5 text-left transition-colors hover:bg-primary/10"
      onClick={() => (dashboardUrl ? openExternalLink(managedVeniceEnableUrl(dashboardUrl)) : onWantApiKey())}
      type="button"
    >
      <span aria-hidden className="arc-border arc-reverse arc-nous" />
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="grid size-5 shrink-0 place-items-center rounded bg-primary/15 text-primary">
            <Codicon name="sparkle" size="0.875rem" />
          </span>
          <span className="text-[length:var(--conversation-text-font-size)] font-semibold">Venice</span>
          <span className="inline-flex items-center gap-1.5 bg-primary px-2 py-0.5 text-[0.64rem] font-semibold uppercase tracking-[0.16em] text-primary-foreground">
            <span aria-hidden="true" className="dither inline-block size-2 shrink-0" />
            Recommended
          </span>
        </div>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{MANAGED_VENICE_PITCH}</p>
      </div>
      <ChevronRight className="size-4 shrink-0 text-primary transition group-hover:translate-x-0.5" />
    </button>
  )
}
