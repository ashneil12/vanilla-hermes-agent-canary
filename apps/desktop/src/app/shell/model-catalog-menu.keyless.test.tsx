// hermes-fork: keyless-provider-guard. Own file (not model-catalog-menu.test.tsx) so an upstream
// edit to that suite can never conflict with the fork's guard test.
//
// Selecting a provider the box has no credentials for would persist a dead provider into
// config.yaml and brick new sessions at agent init; the menu must not offer it.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { DropdownMenu, DropdownMenuContent } from '@/components/ui/dropdown-menu'

import { ModelCatalogMenu, type ModelMenuController } from './model-catalog-menu'

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
  Element.prototype.hasPointerCapture = vi.fn(() => false)
  Element.prototype.releasePointerCapture = vi.fn()
})

afterAll(() => {
  vi.restoreAllMocks()
})

const getGlobalModelOptions = vi.fn()

vi.mock('@/hermes', () => ({
  getGlobalModelOptions: (...args: unknown[]) => getGlobalModelOptions(...args),
  getLocalModelsJobs: vi.fn(async () => ({ jobs: [] })),
  getLocalModelsStatus: vi.fn().mockResolvedValue({ loading: {} }),
  setApiRequestProfile: vi.fn()
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function renderMenu() {
  const controller: ModelMenuController = {
    applyPreset: vi.fn(),
    current: { effort: '', fast: false, model: '', provider: '' },
    presetFor: () => ({}),
    select: vi.fn(),
    setOptions: vi.fn()
  }

  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DropdownMenu open>
        <DropdownMenuContent>
          <ModelCatalogMenu controller={controller} />
        </DropdownMenuContent>
      </DropdownMenu>
    </QueryClientProvider>
  )
}

describe('keyless providers are not selectable in the model menu', () => {
  it('lists authenticated (and unflagged) providers only', async () => {
    getGlobalModelOptions.mockResolvedValue({
      providers: [
        { authenticated: true, models: ['gemini-2.5-flash'], name: 'Google', slug: 'google' },
        { authenticated: false, models: ['claude-sonnet-4'], name: 'Anthropic', slug: 'anthropic' },
        { models: ['gpt-5'], name: 'OpenAI', slug: 'openai' }
      ]
    })
    renderMenu()

    expect(await screen.findByText(/Gemini 2\.5 Flash/i)).toBeTruthy()
    expect(screen.getByText('OpenAI')).toBeTruthy()
    expect(screen.queryByText('Anthropic')).toBeNull()
  })
})
