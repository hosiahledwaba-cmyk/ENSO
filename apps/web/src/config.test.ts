import { describe, expect, it } from 'vitest'
import { resolveConfig } from './config'

describe('resolveConfig', () => {
  it('defaults to the local API when unset', () => {
    expect(resolveConfig({}).apiBaseUrl).toBe('http://localhost:8000')
  })

  it('uses VITE_API_BASE_URL when provided', () => {
    expect(resolveConfig({ VITE_API_BASE_URL: 'https://api.enso.test' }).apiBaseUrl).toBe(
      'https://api.enso.test',
    )
  })

  it.each(['javascript:alert(1)', 'ftp://x', 'api.enso.test'])('rejects %s', (url) => {
    expect(() => resolveConfig({ VITE_API_BASE_URL: url })).toThrow()
  })
})
