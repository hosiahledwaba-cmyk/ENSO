import { useState, useMemo, useEffect } from 'react'
import { config as defaultConfig, type AppConfig } from './config'
import { createApiClient, type SystemStatus } from './api/client'
import { OverviewView } from './views/OverviewView'
import { DashboardView } from './views/DashboardView'
import { DataView } from './views/DataView'
import { FeaturesView } from './views/FeaturesView'
import { ModelsView } from './views/ModelsView'
import { ExperimentsView } from './views/ExperimentsView'
import { ForecastsView } from './views/ForecastsView'
import { PreparednessView } from './views/PreparednessView'
import { SecurityIncidentView } from './views/SecurityIncidentView'
import { ProvenanceView } from './views/ProvenanceView'
import { DiagnosticsView } from './views/DiagnosticsView'

import { ErrorBoundary } from './components/ErrorBoundary'

type WorkbenchTab =
  | 'dashboard'
  | 'overview'
  | 'data'
  | 'features'
  | 'models'
  | 'experiments'
  | 'forecasts'
  | 'preparedness'
  | 'security'
  | 'provenance'
  | 'diagnostics'

interface TabDefinition {
  id: WorkbenchTab
  label: string
  badge?: string
}

const TABS: TabDefinition[] = [
  { id: 'dashboard', label: 'Dashboard', badge: 'Regional Map' },
  { id: 'overview', label: 'Overview' },
  { id: 'forecasts', label: 'Forecasts', badge: 'Inference' },
  { id: 'preparedness', label: 'Preparedness', badge: 'Actions' },
  { id: 'security', label: 'Security', badge: 'Incidents' },
  { id: 'models', label: 'Models', badge: 'Baseline' },
  { id: 'experiments', label: 'Experiments', badge: 'Benchmarks' },
  { id: 'features', label: 'Features', badge: 'Zero-Leakage' },
  { id: 'data', label: 'Data', badge: 'Tiered' },
  { id: 'provenance', label: 'Provenance', badge: 'SHA-256' },
  { id: 'diagnostics', label: 'Diagnostics', badge: 'DB' },
]

export default function App({ config = defaultConfig }: { config?: AppConfig }) {
  const [activeTab, setActiveTab] = useState<WorkbenchTab>('overview')
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null)

  const api = useMemo(
    () => createApiClient({ baseUrl: config.apiBaseUrl }),
    [config.apiBaseUrl],
  )

  useEffect(() => {
    let isMounted = true
    const checkStatus = async () => {
      try {
        const data = await api.getSystemStatus()
        if (isMounted) setSystemStatus(data)
      } catch {
        if (isMounted) setSystemStatus(null)
      }
    }
    void checkStatus()
    const timer = setInterval(() => void checkStatus(), 12000)
    return () => {
      isMounted = false
      clearInterval(timer)
    }
  }, [api])

  return (
    <div className="workbench-shell">
      {/* Top Header */}
      <header className="workbench-header">
        <div className="brand-section">
          <img src="/logo.png" alt="ENSO Shield Logo" className="brand-logo" />
          <div>
            <span className="brand-title">ENSO Shield</span>
            <span className="brand-subtitle">Climate-Intelligence Research Workbench</span>
          </div>
        </div>

        <div className="header-status">
          <div className="status-pill">
            <span
              className={`status-dot ${
                systemStatus ? 'status-dot--green' : 'status-dot--red'
              }`}
            />
            <span>API {systemStatus ? 'Ready' : 'Unreachable'}</span>
          </div>

          <div className="status-pill">
            <span
              className={`status-dot ${
                systemStatus?.database.status === 'connected'
                  ? 'status-dot--green'
                  : 'status-dot--red'
              }`}
            />
            <span>
              PostgreSQL{' '}
              {systemStatus?.database.latency_ms !== null && systemStatus?.database.latency_ms !== undefined
                ? `(${systemStatus.database.latency_ms}ms)`
                : ''}
            </span>
          </div>

          <span style={{ color: 'var(--border-sand)', fontSize: '0.75rem' }}>
            Nov 1 Zero-Lookahead
          </span>
        </div>
      </header>

      {/* Navigation Workflow Bar */}
      <nav className="workflow-nav" aria-label="Workbench sections">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            data-testid={`tab-${tab.id}`}
            className={`nav-item ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
            type="button"
          >
            <span>{tab.label}</span>
            {tab.badge && <span className="nav-badge">{tab.badge}</span>}
          </button>
        ))}
      </nav>

      {/* Main View Area with Component Error Boundary */}
      <main className="workbench-content">
        <ErrorBoundary fallbackTitle="Workbench View Error">
          {activeTab === 'dashboard' && (
            <DashboardView api={api} onNavigate={(tab) => setActiveTab(tab as WorkbenchTab)} />
          )}
          {activeTab === 'overview' && (
            <OverviewView api={api} onNavigate={(tab) => setActiveTab(tab as WorkbenchTab)} />
          )}
          {activeTab === 'forecasts' && <ForecastsView api={api} />}
          {activeTab === 'preparedness' && <PreparednessView api={api} />}
          {activeTab === 'security' && <SecurityIncidentView api={api} />}
          {activeTab === 'models' && <ModelsView api={api} />}
          {activeTab === 'experiments' && <ExperimentsView api={api} />}
          {activeTab === 'features' && <FeaturesView api={api} />}
          {activeTab === 'data' && <DataView api={api} />}
          {activeTab === 'provenance' && <ProvenanceView api={api} />}
          {activeTab === 'diagnostics' && (
            <DiagnosticsView api={api} apiBaseUrl={config.apiBaseUrl} />
          )}
        </ErrorBoundary>
      </main>


      {/* Technical Footer */}
      <footer className="workbench-footer">
        <div>
          ENSO Shield · Containerised Research Workbench · Local Development Stack (Unauthenticated)
        </div>
        <div>
          FastAPI &amp; PostgreSQL Engine · Strict Chronological Partitioning · Research Protocol v1.0
        </div>
      </footer>
    </div>
  )
}
