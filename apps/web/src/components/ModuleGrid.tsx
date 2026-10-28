import type { PlatformModule } from '../data/plannedModules'

export function ModuleGrid({ modules }: { modules: readonly PlatformModule[] }) {
  return (
    <section aria-labelledby="roadmap-heading" className="roadmap">
      <h2 id="roadmap-heading">Platform Capabilities & Status</h2>
      <p className="muted">
        Operational modules have been verified through offline CLI pipelines and automated test suites.
        Model inference and live forecasting endpoints are scheduled for the next API milestone.
      </p>
      <ul className="module-grid">
        {modules.map((m) => (
          <li key={m.id} className="card module" data-testid={`module-${m.id}`}>
            <div className="module__head">
              <h3>{m.title}</h3>
              <span className={`tag tag--${m.status}`}>
                {m.statusLabel}
              </span>
            </div>
            <p>{m.description}</p>
            {(m.verificationEvidence || m.command) && (
              <div className="module__meta">
                {m.verificationEvidence && (
                  <span className="module__evidence">{m.verificationEvidence}</span>
                )}
                {m.command && (
                  <span className="module__command">
                    <code>{m.command}</code>
                  </span>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

