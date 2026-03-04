/**
 * Unit tests for the API client.
 *
 * Uses a mocked `fetch` so these run in jsdom without a live backend.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fetchHealth, analyzeHand, type HealthResponse } from './client'
import type { AnalyzeResponse } from '../types'

const MOCK_HEALTH: HealthResponse = {
  status: 'ok',
  solver_available: false,
  version: '0.1.0',
}

const MOCK_ANALYZE: AnalyzeResponse = {
  advice: 'Raise with QQ.',
  source: 'solver',
  confidence: '0.95',
  mode: 'default',
  cached: false,
  solve_time: 1.5,
  parse_time: 0.2,
  output_level: 'beginner',
  sanity_note: '',
  scenario: null,
  strategy: null,
  structured_advice: null,
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

describe('analyzeHand (mocked)', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve(MOCK_ANALYZE),
      }),
    )
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('sends POST to /api/analyze with JSON body', async () => {
    await analyzeHand({ query: 'I have QQ on BTN' })

    expect(fetch).toHaveBeenCalledWith('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: 'I have QQ on BTN' }),
    })
  })

  it('returns parsed AnalyzeResponse', async () => {
    const data = await analyzeHand({ query: 'I have QQ' })

    expect(data.advice).toBe('Raise with QQ.')
    expect(data.source).toBe('solver')
    expect(data.mode).toBe('default')
  })

  it('sends mode and opponent_notes when provided', async () => {
    await analyzeHand({ query: 'I have AA', mode: 'pro', opponent_notes: 'villain is tight' })

    expect(fetch).toHaveBeenCalledWith('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: 'I have AA', mode: 'pro', opponent_notes: 'villain is tight' }),
    })
  })

  it('throws with detail message on 422 validation error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        statusText: 'Unprocessable Entity',
        json: () => Promise.resolve({ detail: 'query is required', error_code: 'VALIDATION_ERROR' }),
      }),
    )

    await expect(analyzeHand({})).rejects.toThrow('query is required')
  })

  it('throws with status text when error body is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: () => Promise.reject(new Error('not json')),
      }),
    )

    await expect(analyzeHand({ query: 'test' })).rejects.toThrow('Analysis failed: 500 Internal Server Error')
  })

  it('throws on network error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new TypeError('Failed to fetch')),
    )

    await expect(analyzeHand({ query: 'test' })).rejects.toThrow('Failed to fetch')
  })
})
