export type EpistemicClassification =
  | 'HISTORICAL_OBSERVATION'
  | 'MODEL_ESTIMATE'
  | 'OFFICIAL_EXTERNAL_FORECAST'
  | 'SIMULATED_EXPERIMENT'
  | 'OPERATIONAL_TELEMETRY'

interface EpistemicBadgeProps {
  classification: EpistemicClassification
  label?: string
  showDisclaimer?: boolean
  className?: string
}

export function EpistemicBadge({
  classification,
  label,
  showDisclaimer = false,
  className = '',
}: EpistemicBadgeProps) {
  let badgeClass = 'badge-sand'
  let defaultLabel = 'OBSERVATION'
  let icon = '📊'
  let disclaimer = ''

  switch (classification) {
    case 'HISTORICAL_OBSERVATION':
      badgeClass = 'badge-charcoal'
      defaultLabel = 'HISTORICAL OBSERVATION'
      icon = '🏛️'
      disclaimer = 'Archived ground-truth observation from verified historical climate records (CHIRPS/NOAA).'
      break
    case 'OPERATIONAL_TELEMETRY':
      badgeClass = 'badge-ok'
      defaultLabel = 'OPERATIONAL'
      icon = '🛡️'
      disclaimer = 'Live operational telemetry and automated cryptographic audit records.'
      break
    case 'MODEL_ESTIMATE':
      badgeClass = 'badge-terracotta'
      defaultLabel = 'MODEL ESTIMATE'
      icon = '📐'
      disclaimer = 'Probabilistic inference derived from ENSO Shield regularized model and November 1st reference distribution.'
      break
    case 'OFFICIAL_EXTERNAL_FORECAST':
      badgeClass = 'badge-ok'
      defaultLabel = 'OFFICIAL OUTLOOK'
      icon = '🌐'
      disclaimer = 'Consensus seasonal outlook published by SADC Climate Services Centre (SARCOF) or official hydro-met authority.'
      break
    case 'SIMULATED_EXPERIMENT':
      badgeClass = 'badge-warn'
      defaultLabel = 'SIMULATED TEST'
      icon = '⚠️'
      disclaimer = 'SIMULATION ONLY: Synthetic adversarial or perturbation test. Strictly isolated from live operational forecasts.'
      break
  }

  const displayText = label || defaultLabel

  return (
    <span
      className={`epistemic-badge-wrapper ${className}`}
      style={{ display: 'inline-flex', flexDirection: 'column', gap: '0.2rem' }}
    >
      <span
        data-testid={`epistemic-badge-${classification.toLowerCase()}`}
        className={`badge ${badgeClass}`}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.35rem',
          fontSize: '0.7rem',
          fontWeight: 700,
          letterSpacing: '0.04em',
          textTransform: 'uppercase',
          padding: '0.2rem 0.5rem',
          borderRadius: '3px',
        }}
        title={disclaimer}
      >
        <span aria-hidden="true">{icon}</span>
        <span>{displayText}</span>
      </span>
      {showDisclaimer && (
        <span
          className="epistemic-disclaimer-text"
          style={{
            fontSize: '0.68rem',
            color: classification === 'SIMULATED_EXPERIMENT' ? 'var(--accent-terracotta)' : 'var(--text-muted)',
            fontStyle: 'italic',
            lineHeight: 1.25,
            maxWidth: '320px',
          }}
        >
          {disclaimer}
        </span>
      )}
    </span>
  )
}
