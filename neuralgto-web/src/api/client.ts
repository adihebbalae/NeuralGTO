/**
 * NeuralGTO API client.
 *
 * All backend calls go through this module so fetch logic,
 * base-URL handling, and error shapes live in one place.
 */

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
