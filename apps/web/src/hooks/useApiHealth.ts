import { useCallback, useEffect, useState } from 'react'
import { fetchReadiness, type ReadinessResponse } from '../api/health'

export type HealthState =
  | { kind: 'loading' }
  | { kind: 'online'; data: ReadinessResponse; checkedAt: Date }
  | { kind: 'degraded'; data: ReadinessResponse; checkedAt: Date }
  | { kind: 'offline'; reason: string; checkedAt: Date }

export function useApiHealth(baseUrl: string): { state: HealthState; refresh: () => void } {
  const [state, setState] = useState<HealthState>({ kind: 'loading' })
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    fetchReadiness(baseUrl, controller.signal)
      .then((data) => {
        if (data.status === 'ok') {
          setState({ kind: 'online', data, checkedAt: new Date() })
        } else {
          setState({ kind: 'degraded', data, checkedAt: new Date() })
        }
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        const reason = err instanceof Error ? err.message : 'Unknown error'
        setState({ kind: 'offline', reason, checkedAt: new Date() })
      })
    return () => controller.abort()
  }, [baseUrl, nonce])

  const refresh = useCallback(() => {
    setState({ kind: 'loading' })
    setNonce((n) => n + 1)
  }, [])

  return { state, refresh }
}

