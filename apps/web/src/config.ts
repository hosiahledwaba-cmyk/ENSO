/** Build-time configuration. Values come from `VITE_*` environment variables only. */

const DEFAULT_API_BASE_URL = 'http://localhost:8000'

export interface AppConfig {
  apiBaseUrl: string
}

export function resolveConfig(env: Record<string, string | undefined>): AppConfig {
  const raw = env.VITE_API_BASE_URL?.trim()
  const apiBaseUrl = raw && raw.length > 0 ? raw : DEFAULT_API_BASE_URL
  if (!/^https?:\/\//.test(apiBaseUrl)) {
    throw new Error(`VITE_API_BASE_URL must be an http(s) URL, got: ${apiBaseUrl}`)
  }
  return { apiBaseUrl }
}

export const config: AppConfig = resolveConfig(import.meta.env)
