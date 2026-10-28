/** Typed client for API health and readiness endpoints. */

export interface HealthResponse {
  status: 'ok'
  service: string
  version: string
}

export interface DatabaseStatus {
  status: 'connected' | 'unreachable' | 'disabled'
  latency_ms: number | null
  detail?: string | null
}

export interface ReadinessResponse {
  status: 'ok' | 'degraded'
  service: string
  version: string
  database: DatabaseStatus
}

export class HealthCheckError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'HealthCheckError'
  }
}

export function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return v.status === 'ok' && typeof v.service === 'string' && typeof v.version === 'string'
}

export function isReadinessResponse(value: unknown): value is ReadinessResponse {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  if (v.status !== 'ok' && v.status !== 'degraded') return false
  if (typeof v.service !== 'string' || typeof v.version !== 'string') return false
  if (typeof v.database !== 'object' || v.database === null) return false
  const db = v.database as Record<string, unknown>
  return db.status === 'connected' || db.status === 'unreachable' || db.status === 'disabled'
}

/** Strips trailing slashes so `${base}/health` is always well-formed. */
export function normaliseBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, '')
}

export async function fetchHealth(
  baseUrl: string,
  signal?: AbortSignal,
  fetchImpl: typeof fetch = fetch,
): Promise<HealthResponse> {
  let response: Response
  try {
    response = await fetchImpl(`${normaliseBaseUrl(baseUrl)}/health`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      credentials: 'omit',
      signal,
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new HealthCheckError('API unreachable')
  }

  if (!response.ok) {
    throw new HealthCheckError(`API responded with HTTP ${response.status}`)
  }

  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new HealthCheckError('API returned a non-JSON response')
  }

  if (!isHealthResponse(body)) {
    throw new HealthCheckError('API returned an unexpected health payload')
  }
  return body
}

export async function fetchReadiness(
  baseUrl: string,
  signal?: AbortSignal,
  fetchImpl: typeof fetch = fetch,
): Promise<ReadinessResponse> {
  let response: Response
  try {
    response = await fetchImpl(`${normaliseBaseUrl(baseUrl)}/health/ready`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      credentials: 'omit',
      signal,
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new HealthCheckError('API unreachable')
  }

  if (!response.ok && response.status !== 503) {
    throw new HealthCheckError(`API responded with HTTP ${response.status}`)
  }

  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new HealthCheckError('API returned a non-JSON response')
  }

  if (!isReadinessResponse(body)) {
    throw new HealthCheckError('API returned an unexpected readiness payload')
  }
  return body
}

