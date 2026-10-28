import type { HealthState } from '../hooks/useApiHealth'

interface Props {
  state: HealthState
  apiBaseUrl: string
  onRefresh: () => void
}

const LABELS: Record<HealthState['kind'], string> = {
  loading: 'Checking…',
  online: 'Online',
  degraded: 'Degraded',
  offline: 'Unreachable',
}

export function ApiStatusCard({ state, apiBaseUrl, onRefresh }: Props) {
  return (
    <section className="card status-card" aria-labelledby="api-status-heading">
      <header className="card__header">
        <h2 id="api-status-heading">API readiness</h2>
        <span className={`pill pill--${state.kind}`} role="status" data-testid="api-status">
          <span className="pill__dot" aria-hidden="true" />
          {LABELS[state.kind]}
        </span>
      </header>

      <dl className="kv">
        <dt>Endpoint</dt>
        <dd>
          <code>{apiBaseUrl}/health/ready</code>
        </dd>
        {(state.kind === 'online' || state.kind === 'degraded') && (
          <>
            <dt>Service</dt>
            <dd>{state.data.service}</dd>
            <dt>Version</dt>
            <dd>{state.data.version}</dd>
            <dt>Database</dt>
            <dd data-testid="db-status">
              {state.data.database.status === 'connected' && (
                <span className="text-ok">
                  Connected{state.data.database.latency_ms !== null ? ` (${state.data.database.latency_ms} ms)` : ''}
                </span>
              )}
              {state.data.database.status === 'unreachable' && (
                <span className="text-err">
                  Unreachable{state.data.database.detail ? ` (${state.data.database.detail})` : ''}
                </span>
              )}
              {state.data.database.status === 'disabled' && (
                <span className="text-muted">Disabled (unconfigured)</span>
              )}
            </dd>
          </>
        )}
        {state.kind === 'offline' && (
          <>
            <dt>Reason</dt>
            <dd data-testid="api-status-reason">{state.reason}</dd>
          </>
        )}
        {state.kind !== 'loading' && (
          <>
            <dt>Checked</dt>
            <dd>{state.checkedAt.toLocaleTimeString()}</dd>
          </>
        )}
      </dl>

      <button
        id="api-status-refresh"
        type="button"
        className="btn"
        onClick={onRefresh}
        disabled={state.kind === 'loading'}
      >
        Re-check
      </button>

      <p className="status-card__note muted">
        Swagger UI (<code>/docs</code>) exposes operational <code>/health</code> and <code>/health/ready</code> probes.
        Model inference and dataset catalog endpoints are scheduled for the next API milestone.
      </p>
    </section>
  )
}

