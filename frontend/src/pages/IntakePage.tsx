import { useEffect } from 'react'
import { useAppDispatch, useAppSelector } from '@/app/store'
import { ComplaintForm } from '@/components/intake/ComplaintForm'
import { AssistantPanel } from '@/components/intake/AssistantPanel'
import { RiskAssessment } from '@/components/intake/RiskAssessment'
import { Icon } from '@/components/Icon'
import { Callout, SeverityChip } from '@/components/ui/primitives'
import { systemNote } from '@/features/copilot/copilotSlice'
import '@/components/intake/intake.css'

const BAND_COLOR: Record<string, string> = {
  Low: 'var(--band-low)', Moderate: 'var(--band-moderate)',
  High: 'var(--band-high)', Severe: 'var(--band-severe)',
}

const today = () => new Date().toLocaleDateString('en-GB', {
  day: '2-digit', month: 'short', year: 'numeric',
})

/** The one-line verdict the analyst sees the moment the agent finishes. */
function VerdictStrip() {
  const { risk, phase, engine, durationMs, models } = useAppSelector((s) => s.intake)
  if (phase !== 'complete' || !risk) return null
  const colour = BAND_COLOR[risk.band] ?? 'var(--accent)'

  return (
    <div className="verdict" style={{ ['--band' as string]: colour }}>
      <div>
        <div className="t-label" style={{ marginBottom: 3 }}>Composite risk</div>
        <div className="verdict-score">{risk.score.toFixed(0)}<small>/100</small></div>
      </div>
      <div className="grow">
        <div className="row" style={{ gap: 8, marginBottom: 4 }}>
          <SeverityChip value={risk.severity} />
          <span className="chip" style={{ color: colour, borderColor: colour }}>{risk.band}</span>
          {risk.regulatory_flags.length > 0 && (
            <span className="chip chip-critical">
              <Icon name="alert" size={10} />
              {risk.regulatory_flags.length} regulatory trigger
              {risk.regulatory_flags.length > 1 ? 's' : ''}
            </span>
          )}
        </div>
        <div className="t-xs t-muted">
          Assessed in {(durationMs / 1000).toFixed(2)}s by{' '}
          {engine === 'groq' ? `Groq ${models.reasoning ?? ''}` : 'the deterministic rule engine'}
          {risk.recommended_tat_days && ` · investigation due in ${risk.recommended_tat_days} days`}
        </div>
      </div>
      <button
        className="btn btn-sm"
        onClick={() => document.getElementById('assessment')
          ?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
      >
        <Icon name="arrow" size={12} style={{ transform: 'rotate(90deg)' }} />
        Full assessment
      </button>
    </div>
  )
}

export function IntakePage() {
  const dispatch = useAppDispatch()
  const { warnings, error, savedReference, phase } = useAppSelector((s) => s.intake)
  const status = useAppSelector((s) => s.system.status)

  useEffect(() => {
    if (phase === 'complete') dispatch(systemNote('Extraction complete — the form has been populated.'))
  }, [phase, dispatch])

  return (
    <div className="intake">
      <header className="doc-head">
        <div className="doc-title">
          <div>
            <h1 className="t-display">Log Customer Complaint</h1>
            <p>
              Record, classify and triage a market complaint for API and finished-dosage-form
              product under the site quality management system.
            </p>
          </div>
        </div>

        <dl className="doc-strip">
          <div className="doc-cell"><dt>Document</dt><dd className="t-mono">QMS-CMP-001</dd></div>
          <div className="doc-cell"><dt>Revision</dt><dd className="t-mono">04</dd></div>
          <div className="doc-cell"><dt>Effective</dt><dd>{today()}</dd></div>
          <div className="doc-cell"><dt>Owner</dt><dd>Quality Assurance</dd></div>
          <div className="doc-cell"><dt>Reference</dt>
            <dd className="t-mono">{savedReference ?? 'Unassigned'}</dd></div>
        </dl>
      </header>

      {status === 'offline' && (
        <Callout tone="critical" icon="alert">
          <b>The API is not reachable.</b> Start the backend from the <code>backend/</code>{' '}
          directory with <code className="t-mono">uvicorn app.main:app --reload</code>.
        </Callout>
      )}

      {error && <Callout tone="critical" icon="alert">{error}</Callout>}
      {warnings.map((warning) => (
        <Callout key={warning} tone="major" icon="alert">{warning}</Callout>
      ))}

      <VerdictStrip />

      <div className="intake-split">
        <ComplaintForm />
        <AssistantPanel />
      </div>

      <RiskAssessment />
    </div>
  )
}
