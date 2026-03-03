/**
 * Unit tests for the API client.
 *
 * Uses a mocked `fetch` so these run in jsdom without a live backend.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fetchHealth, type HealthResponse } from './client'

const MOCK_HEALTH: HealthResponse = {
  status: 'ok',
  solver_available: false,
  version: '0.1.0',
}

describe('fetchHealth (mocked)', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve(MOCK_HEALTH),
      }),
    )
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('calls /api/health and returns parsed JSON', async () => {
    const data = await fetchHealth()

    expect(fetch).toHaveBeenCalledWith('/api/health')
    expect(data).toEqual(MOCK_HEALTH)
  })

  it('has required fields in response shape', async () => {
    const data = await fetchHealth()

    expect(data).toHaveProperty('status')
    expect(data).toHaveProperty('solver_available')
    expect(data).toHaveProperty('version')
    expect(typeof data.status).toBe('string')
    expect(typeof data.solver_available).toBe('boolean')
    expect(typeof data.version).toBe('string')
  })

  it('throws on non-200 response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        statusText: 'Bad Gateway',
      }),
    )

    await expect(fetchHealth()).rejects.toThrow('Health check failed: 502 Bad Gateway')
  })
})
