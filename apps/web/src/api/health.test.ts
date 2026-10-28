import { describe, expect, it, vi } from 'vitest'
import {
  fetchHealth,
  fetchReadiness,
  HealthCheckError,
  isHealthResponse,
  isReadinessResponse,
  normaliseBaseUrl,
} from './health'

const okBody = { status: 'ok', service: 'enso-shield-api', version: '0.1.0' }

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('isHealthResponse', () => {
  it('accepts a valid payload', () => {
    expect(isHealthResponse(okBody)).toBe(true)
  })

  it.each([null, 'ok', {}, { ...okBody, status: 'degraded' }, { ...okBody, version: 1 }])(
    'rejects %j',
    (value) => {
      expect(isHealthResponse(value)).toBe(false)
    },
  )
})

describe('normaliseBaseUrl', () => {
  it('strips trailing slashes', () => {
    expect(normaliseBaseUrl('http://api.test///')).toBe('http://api.test')
  })
})

describe('fetchHealth', () => {
  it('requests /health without credentials and returns the payload', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(okBody))
    await expect(fetchHealth('http://api.test/', undefined, fetchImpl)).resolves.toEqual(okBody)
    const [url, init] = fetchImpl.mock.calls[0]
    expect(url).toBe('http://api.test/health')
    expect(init?.credentials).toBe('omit')
    expect(init?.method).toBe('GET')
  })

  it('throws on non-2xx responses', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({}, 503))
    await expect(fetchHealth('http://api.test', undefined, fetchImpl)).rejects.toThrow(
      'API responded with HTTP 503',
    )
  })

  it('throws on network failure', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(fetchHealth('http://api.test', undefined, fetchImpl)).rejects.toBeInstanceOf(
      HealthCheckError,
    )
  })

  it('throws on non-JSON body', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response('<html>', { status: 200 }))
    await expect(fetchHealth('http://api.test', undefined, fetchImpl)).rejects.toThrow(
      'non-JSON',
    )
  })

  it('throws on an unexpected payload shape', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({ status: 'ok' }))
    await expect(fetchHealth('http://api.test', undefined, fetchImpl)).rejects.toThrow(
      'unexpected health payload',
    )
  })
})

const okReadyBody = {
  status: 'ok',
  service: 'enso-shield-api',
  version: '0.1.0',
  database: { status: 'connected', latency_ms: 1.5 },
}

describe('isReadinessResponse', () => {
  it('accepts valid connected and disabled readiness payloads', () => {
    expect(isReadinessResponse(okReadyBody)).toBe(true)
    expect(
      isReadinessResponse({
        status: 'ok',
        service: 'enso-shield-api',
        version: '0.1.0',
        database: { status: 'disabled', latency_ms: null },
      }),
    ).toBe(true)
  })

  it('accepts degraded payload with unreachable database', () => {
    expect(
      isReadinessResponse({
        status: 'degraded',
        service: 'enso-shield-api',
        version: '0.1.0',
        database: { status: 'unreachable', latency_ms: null, detail: 'timeout' },
      }),
    ).toBe(true)
  })

  it('rejects malformed payloads', () => {
    expect(isReadinessResponse(null)).toBe(false)
    expect(isReadinessResponse({})).toBe(false)
    expect(
      isReadinessResponse({
        status: 'unknown',
        service: 'api',
        version: '1',
        database: { status: 'connected' },
      }),
    ).toBe(false)
  })
})

describe('fetchReadiness', () => {
  it('requests /health/ready without credentials and parses payload', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(okReadyBody))
    await expect(fetchReadiness('http://api.test/', undefined, fetchImpl)).resolves.toEqual(
      okReadyBody,
    )
    const [url, init] = fetchImpl.mock.calls[0]
    expect(url).toBe('http://api.test/health/ready')
    expect(init?.credentials).toBe('omit')
  })

  it('accepts 503 with degraded readiness payload', async () => {
    const degradedBody = {
      status: 'degraded',
      service: 'enso-shield-api',
      version: '0.1.0',
      database: { status: 'unreachable', latency_ms: null, detail: 'connection refused' },
    }
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(degradedBody, 503))
    await expect(fetchReadiness('http://api.test', undefined, fetchImpl)).resolves.toEqual(
      degradedBody,
    )
  })

  it('throws on 500 internal server error', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response('error', { status: 500 }))
    await expect(fetchReadiness('http://api.test', undefined, fetchImpl)).rejects.toThrow(
      'API responded with HTTP 500',
    )
  })
})

