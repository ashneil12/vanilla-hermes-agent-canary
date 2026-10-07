import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { VeniceRecommendedCard } from './venice-recommended-card'

const getStatus = vi.hoisted(() => vi.fn())
const openExternalLink = vi.hoisted(() => vi.fn())

vi.mock('@/hermes', () => ({ getStatus }))
vi.mock('@/lib/external-link', () => ({ openExternalLink }))

beforeEach(() => {
  getStatus.mockReset()
  openExternalLink.mockReset()
})

afterEach(cleanup)

describe('VeniceRecommendedCard', () => {
  it('deep-links the managed-Venice enable flow on the control-plane dashboard from /api/status', async () => {
    getStatus.mockResolvedValue({ dashboard_url: 'https://hivra.example/' })
    const onWantApiKey = vi.fn()

    render(<VeniceRecommendedCard onWantApiKey={onWantApiKey} />)
    await waitFor(() => expect(getStatus).toHaveBeenCalled())
    await new Promise(resolve => setTimeout(resolve, 0))
    fireEvent.click(screen.getByRole('button'))

    expect(openExternalLink).toHaveBeenCalledWith(
      'https://hivra.example/dashboard/billing?managedVenice=deposit&wallet=hermesos'
    )
    expect(onWantApiKey).not.toHaveBeenCalled()
  })

  it.each([
    ['no dashboard_url (local dev)', { dashboard_url: null }],
    ['a status failure', null]
  ])('falls back to the API-key path on %s, never a dead end', async (_label, status) => {
    if (status) {
      getStatus.mockResolvedValue(status)
    } else {
      getStatus.mockRejectedValue(new Error('offline'))
    }

    const onWantApiKey = vi.fn()

    render(<VeniceRecommendedCard onWantApiKey={onWantApiKey} />)
    await waitFor(() => expect(getStatus).toHaveBeenCalled())
    await new Promise(resolve => setTimeout(resolve, 0))
    fireEvent.click(screen.getByRole('button'))

    expect(onWantApiKey).toHaveBeenCalledOnce()
    expect(openExternalLink).not.toHaveBeenCalled()
  })

  it('holds the Recommended slot and survives a synchronous bridge throw', () => {
    getStatus.mockImplementation(() => {
      throw new Error('no bridge')
    })

    render(<VeniceRecommendedCard onWantApiKey={vi.fn()} />)

    expect(screen.getByText('Recommended')).toBeTruthy()
  })
})
