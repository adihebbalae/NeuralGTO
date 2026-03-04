/**
 * NeuralGTO API client.
 *
 * All backend calls go through this module so fetch logic,
 * base-URL handling, and error shapes live in one place.
 */

import type { AnalyzeRequest, AnalyzeResponse, ApiError, ReanalyzeStreetRequest } from '../types'

/** Health-check response shape (mirrors backend HealthResponse). */
export interface HealthResponse {
  status: string
  solver_available: boolean
  version: string
}

/**
 * Base URL for API requests.
 * In dev the Vite proxy rewrites `/api` → `http://localhost:8000/api`,
 * so we can use a relative path.  In production this could be overridden
 * via `VITE_API_URL`.
 */
const BASE_URL: string = import.meta.env.VITE_API_URL ?? ''

/**
 * Fetch the backend health-check endpoint.
 *
 * @returns Parsed {@link HealthResponse}
 * @throws  {Error} On network failure or non-200 status
 */
export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${BASE_URL}/api/health`)
  if (!res.ok) {
    throw new Error(`Health check failed: ${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<HealthResponse>
}

/**
 * Submit a poker hand for GTO analysis.
 *
 * @param request - Scenario description (NL text or structured fields)
 * @returns Parsed {@link AnalyzeResponse} with advice + structured breakdown
 * @throws  {Error} With human-readable message on 4xx/5xx responses
 */
export async function analyzeHand(
  request: AnalyzeRequest,
): Promise<AnalyzeResponse> {
  const res = await fetch(`${BASE_URL}/api/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })

  if (!res.ok) {
    let message = `Analysis failed: ${res.status} ${res.statusText}`
    try {
      const err = (await res.json()) as ApiError
      if (err.detail) message = err.detail
    } catch {
      // JSON parse failed — keep the status-line message
    }
    throw new Error(message)
  }

  return res.json() as Promise<AnalyzeResponse>
}

/**
 * Re-run analysis with new board cards (interactive card picker).
 *
 * @param request - Current scenario + new board cards
 * @returns Parsed {@link AnalyzeResponse} with updated advice for the new street
 * @throws  {Error} With human-readable message on 4xx/5xx responses
 */
export async function reanalyzeStreet(
  request: ReanalyzeStreetRequest,
): Promise<AnalyzeResponse> {
  const res = await fetch(`${BASE_URL}/api/reanalyze-street`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })

  if (!res.ok) {
    let message = `Reanalysis failed: ${res.status} ${res.statusText}`
    try {
      const err = (await res.json()) as ApiError
      if (err.detail) message = err.detail
    } catch {
      // JSON parse failed — keep the status-line message
    }
    throw new Error(message)
  }

  return res.json() as Promise<AnalyzeResponse>
}
