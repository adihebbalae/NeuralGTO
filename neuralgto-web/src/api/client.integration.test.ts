/**
 * Integration test: frontend → FastAPI backend.
 *
 * Validates the full stack wiring:
 *   React dev server (Vite proxy) → FastAPI /api/health
 *
 * Prerequisites:
 *   1. FastAPI running:  cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000
 *   2. (Optional) Vite running: cd neuralgto-web && npm run dev
 *
 * This test hits the backend directly on port 8000 to verify CORS
 * headers and response shape.  It is skipped automatically when the
 * backend is not reachable (CI-safe).
 *
 * @vitest-environment node
 */

import { describe, it, expect } from 'vitest'

const BACKEND_URL = 'http://localhost:8000'
const FRONTEND_ORIGIN = 'http://localhost:5173'

/**
 * Probe whether the backend is reachable.
 * Returns true if /api/health responds within 2 s.
 */
async function isBackendUp(): Promise<boolean> {
  try {
    const res = await fetch(`${BACKEND_URL}/api/health`, {
      signal: AbortSignal.timeout(2000),
    })
    return res.ok
  } catch {
    return false
  }
}

describe('Frontend ↔ Backend integration', () => {
  it('GET /api/health returns expected shape', async () => {
    const up = await isBackendUp()
    if (!up) {
      console.warn('⚠ Backend not running on :8000 — skipping integration test')
      return
    }

    const res = await fetch(`${BACKEND_URL}/api/health`)
    expect(res.ok).toBe(true)
    expect(res.headers.get('content-type')).toContain('application/json')

    const data = await res.json()
    console.log('✓ /api/health response:', JSON.stringify(data))

    expect(data).toEqual({
      status: 'ok',
      solver_available: false,
      version: '0.1.0',
    })
  })

  it('CORS allows requests from frontend origin', async () => {
    const up = await isBackendUp()
    if (!up) {
      console.warn('⚠ Backend not running on :8000 — skipping CORS test')
      return
    }

    // Simulate browser preflight
    const res = await fetch(`${BACKEND_URL}/api/health`, {
      method: 'OPTIONS',
      headers: {
        Origin: FRONTEND_ORIGIN,
        'Access-Control-Request-Method': 'GET',
      },
    })

    expect(res.status).toBeLessThan(400)

    const allowOrigin = res.headers.get('access-control-allow-origin')
    expect(allowOrigin).toBe(FRONTEND_ORIGIN)
  })

  it('CORS blocks requests from unknown origin', async () => {
    const up = await isBackendUp()
    if (!up) {
      console.warn('⚠ Backend not running on :8000 — skipping CORS block test')
      return
    }

    const res = await fetch(`${BACKEND_URL}/api/health`, {
      method: 'OPTIONS',
      headers: {
        Origin: 'http://evil.example.com',
        'Access-Control-Request-Method': 'GET',
      },
    })

    const allowOrigin = res.headers.get('access-control-allow-origin')
    // Should NOT echo back the evil origin
    expect(allowOrigin).not.toBe('http://evil.example.com')
  })
})
