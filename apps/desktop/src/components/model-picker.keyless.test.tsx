// hermes-fork: keyless-provider-guard. Own file so an upstream edit to model-picker.test.tsx can
// never conflict with the fork's guard test (see app/shell/model-catalog-menu.keyless.test.tsx).
import type { ModelOptionsResult } from '@hermes/shared'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '@/i18n'
import { $localModelsEnabled } from '@/store/local-models-flag'
import { $localRuntimeJobs } from '@/store/local-runtime-jobs'
import { stubMenuDomApis, stubResizeObserver } from '@/test/jsdom'

import { ModelPickerDialog } from './model-picker'

vi.mock('@/hermes', () => ({
  getLocalModelsStatus: vi.fn().mockResolvedValue({ loading: {} })
}))
vi.mock('@/lib/model-options', async importOriginal => ({
  ...(await importOriginal<Record<string, unknown>>()),
  requestModelOptions: vi.fn()
}))

import { requestModelOptions } from '@/lib/model-options'

stubResizeObserver()
stubMenuDomApis()

const OPTIONS: ModelOptionsResult = {
  providers: [
    { slug: 'nous', name: 'Nous', models: ['Hermes-4.5'], authenticated: true },
    { slug: 'anthropic', name: 'Anthropic', models: ['claude-sonnet-4'], authenticated: false }
  ]
}

beforeEach(() => {
  vi.mocked(requestModelOptions).mockResolvedValue(OPTIONS)
  $localRuntimeJobs.set([])
  $localModelsEnabled.set(true)
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('ModelPickerDialog keyless providers', () => {
  it('omits a provider the box has no credentials for, even when it surfaces models', async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <I18nProvider>
          <ModelPickerDialog
            currentModel="Hermes-4.5"
            currentProvider="nous"
            onOpenChange={() => undefined}
            onSelect={() => undefined}
            open
          />
        </I18nProvider>
      </QueryClientProvider>
    )

    expect(await screen.findByText('Hermes-4.5')).toBeTruthy()
    expect(screen.queryByText('claude-sonnet-4')).toBeNull()
  })
})
