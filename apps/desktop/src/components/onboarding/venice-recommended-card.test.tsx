import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { VeniceRecommendedCard } from './venice-recommended-card'

const hermesApi = vi.hoisted(() => vi.fn())
const openExternalLink = vi.hoisted(() => vi.fn())

vi.mock('@/hermes', () => ({ hermesApi }))
vi.mock('@/lib/external-link', () => ({ openExternalLink }))

beforeEach(() => {
  hermesApi.mockReset()
  openExternalLink.mockReset()
})

afterEach(cleanup)

describe('VeniceRecommendedCard', () => {
  it('deep-links the managed-Venice enable flow on the control-plane dashboard from /api/hivra/config', async () => {
    hermesApi.mockResolvedValue({ dashboard_url: 'https://hivra.example/' })
    const onWantApiKey = vi.fn()

    render(<VeniceRecommendedCard onWantApiKey={onWantApiKey} />)
    await waitFor(() => expect(hermesApi).toHaveBeenCalled())
    await new Promise(resolve => setTimeout(resolve, 0))
    fireEvent.click(screen.getByRole('button'))

    expect(hermesApi).toHaveBeenCalledWith({ path: '/api/hivra/config' })
    expect(openExternalLink).toHaveBeenCalledWith(
      'https://hivra.example/dashboard/billing?managedVenice=deposit&wallet=hermesos'
    )
    expect(onWantApiKey).not.toHaveBeenCalled()
  })

  it.each([
    ['no dashboard_url (local dev)', { dashboard_url: null }],
    ['a config failure', null]
  ])('falls back to the API-key path on %s, never a dead end', async (_label, status) => {
    if (status) {
      hermesApi.mockResolvedValue(status)
    } else {
      hermesApi.mockRejectedValue(new Error('offline'))
    }

    const onWantApiKey = vi.fn()

    render(<VeniceRecommendedCard onWantApiKey={onWantApiKey} />)
    await waitFor(() => expect(hermesApi).toHaveBeenCalled())
    await new Promise(resolve => setTimeout(resolve, 0))
    fireEvent.click(screen.getByRole('button'))

    expect(onWantApiKey).toHaveBeenCalledOnce()
    expect(openExternalLink).not.toHaveBeenCalled()
  })

  it('holds the Recommended slot and survives a synchronous bridge throw', () => {
    hermesApi.mockImplementation(() => {
      throw new Error('no bridge')
    })

    render(<VeniceRecommendedCard onWantApiKey={vi.fn()} />)

    expect(screen.getByText('Recommended')).toBeTruthy()
  })

  it("keeps the words 'API key' out of the button text (upstream's onboarding e2e wants exactly one /api key/i button)", () => {
    hermesApi.mockResolvedValue({ dashboard_url: null })
    render(<VeniceRecommendedCard onWantApiKey={vi.fn()} />)

    expect(screen.getByRole('button').textContent ?? '').not.toMatch(/api key/i)
  })
})
