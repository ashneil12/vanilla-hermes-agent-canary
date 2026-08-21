import { useStore } from '@nanostores/react'
import { useEffect } from 'react'

import { BrandMark } from '@/components/brand-mark'
// hermes-fork: HermesOS is centrally managed (image rebuild + redeploy), so the
// in-app self-update controls are intentionally absent. We keep ONLY the imports
// the passive "automatic updates" note needs — do NOT re-take upstream's
// self-update UI imports (Button/Codicon/checkUpdates/startActiveUpdate/etc.).
import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'
import { AlertTriangle, ExternalLink, RefreshCw } from '@/lib/icons'
import { $desktopVersion, refreshDesktopVersion } from '@/store/updates'

import { ListRow, SectionHeading, SettingsContent } from './primitives'
import { UninstallSection } from './uninstall-section'

const INSTALLER_URL = 'https://hermes-agent.nousresearch.com/'
export function AboutSettings() {
  const { t } = useI18n()
  const a = t.settings.about
  const version = useStore($desktopVersion)

  // The version atom is loaded once at app boot; re-read on mount so opening
  // About always reflects the running build.
  useEffect(() => {
    void refreshDesktopVersion()
  }, [])

  return (
    <SettingsContent>
      <div className="flex flex-col items-center gap-3 pt-6 pb-2 text-center">
        <BrandMark className="size-16" />
        <div>
          <h2 className="text-lg font-semibold tracking-tight">{a.heading}</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {version?.appVersion ? a.version(version.appVersion) : a.versionUnavailable}
          </p>
        </div>
        {version?.bundleOutOfSync && (
          <div className="mx-auto w-full max-w-2xl rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-left text-sm">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
              <div className="min-w-0">
                <p className="font-medium">{a.bundleOutOfSync}</p>
                <p className="mt-1 text-xs text-muted-foreground">{a.bundleOutOfSyncDesc}</p>
                <Button asChild className="mt-2" size="sm" variant="textStrong">
                  <a
                    href={INSTALLER_URL}
                    onClick={event => {
                      event.preventDefault()
                      void window.hermesDesktop?.openExternal?.(INSTALLER_URL)
                    }}
                    rel="noreferrer"
                    target="_blank"
                  >
                    <ExternalLink className="size-3" />
                    {a.bundleOutOfSyncAction}
                  </a>
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="mx-auto mt-4 w-full max-w-2xl">
        <SectionHeading icon={RefreshCw} title={a.updates} />

        {/* hermes-fork (case D — kept over upstream's 06-24/25 self-update
            overlay re-add): HermesOS is managed — the agent/backend is updated
            centrally (image rebuild + redeploy). The in-app self-update controls
            (check / "see what's new" / "update now") were removed so users aren't
            funnelled into the `hermes update` path; this stays as a passive,
            non-actionable note. */}
        <ListRow description={a.automaticUpdatesDesc} title={a.automaticUpdates} />

        <UninstallSection />
      </div>
    </SettingsContent>
  )
}
