import { useNavigate } from 'react-router-dom'
import { useAppDispatch, useAppSelector } from '@/app/store'
import { dismissDuplicate, fieldChanged, reassess } from '@/features/intake/intakeSlice'
import { Icon } from '../Icon'
import { Callout, RiskMeter, SeverityChip } from '../ui/primitives'
import './intake.css'

const FLAG_LABEL: Record<string, string> = {
  field_alert_report: 'Field Alert Report',
  adverse_event_report: 'Adverse Event Report',
  recall_assessment: 'Recall Assessment',
  regulatory_notification: 'Authority Notification',
}

const BAND_COLOR: Record<string, string> = {
  Low: 'var(--band-low)', Moderate: 'var(--band-moderate)',
  High: 'var(--band-high)', Severe: 'var(--band-severe)',
}

/* ── 1. Risk ───────────────────────────────────────────────────────────────── */
function RiskCard() {
  const dispatch = useAppDispatch()
  const risk = useAppSelector((s) => s.intake.risk)
  const running = useAppSelector((s) => s.intake.phase === 'running')
  if (!risk) return null

  return (
    <div className="card">
      <div className="card-head">
        <Icon name="shield" size={15} style={{ color: BAND_COLOR[risk.band] }} />
        <span className="t-label grow">AI Copilot · Risk Assessment</span>
        <button className="btn btn-ghost btn-sm" disabled={running}
          onClick={() => dispatch(reassess())} title="Re-run the assessment against your edits">
          <Icon name="reset" size={12} /> Re-assess
        </button>
      </div>

      <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
        <div className="row" style={{ alignItems: 'flex-end', gap: 'var(--sp-5)' }}>
          <div>
            <div className="t-label" style={{ marginBottom: 4 }}>Composite risk</div>
            <div style={{
              fontSize: 34, fontWeight: 600, letterSpacing: '-.035em', lineHeight: 1,
              fontVariantNumeric: 'tabular-nums', color: BAND_COLOR[risk.band],
            }}>
              {risk.score.toFixed(0)}
              <span style={{ fontSize: 13, color: 'var(--ink-4)', fontWeight: 500 }}>/100</span>
            </div>
          </div>
          <div className="grow"><RiskMeter score={risk.score} band={risk.band} /></div>
        </div>

        <div className="doc-strip">
          <div className="doc-cell">
            <dt>GMP Severity</dt>
            <dd><SeverityChip value={risk.severity} /></dd>
          </div>
          <div className="doc-cell">
            <dt>Priority</dt>
            <dd>{risk.priority ?? '—'}</dd>
          </div>
          <div className="doc-cell">
            <dt>Target TAT</dt>
            <dd>{risk.recommended_tat_days ? `${risk.recommended_tat_days} days` : '—'}</dd>
          </div>
        </div>

        {risk.override && (
          <Callout tone="major" icon="alert">
            <b>Rule-engine escalation.</b> The deterministic safety rule raised this
            classification above the model's assessment. Review the drivers before accepting.
          </Callout>
        )}

        {risk.rationale && (
          <p className="t-sm" style={{ color: 'var(--ink-2)', lineHeight: 1.6 }}>{risk.rationale}</p>
        )}

        {risk.drivers.length > 0 && (
          <div>
            <div className="t-label" style={{ marginBottom: 4 }}>Contributing factors</div>
            {risk.drivers.map((driver, index) => (
              <div className="driver" key={index}>
                <div className="driver-head">
                  <span className="t-sm">{driver.factor}</span>
                  <span className="driver-w">{driver.weight.toFixed(2)}</span>
                </div>
                <div className="driver-bar">
                  <i style={{ width: `${driver.weight * 100}%`, background: BAND_COLOR[risk.band] }} />
                </div>
                {driver.evidence && (
                  <div className="t-xs t-muted" style={{ marginTop: 5, fontStyle: 'italic' }}>
                    “{driver.evidence}”
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {(risk.patient_safety_impact || risk.batch_impact) && (
          <div style={{ display: 'grid', gap: 'var(--sp-3)' }}>
            {risk.patient_safety_impact && (
              <div>
                <div className="t-label">Patient safety impact</div>
                <p className="t-sm" style={{ marginTop: 3 }}>{risk.patient_safety_impact}</p>
              </div>
            )}
            {risk.batch_impact && (
              <div>
                <div className="t-label">Batch / market exposure</div>
                <p className="t-sm" style={{ marginTop: 3 }}>{risk.batch_impact}</p>
              </div>
            )}
          </div>
        )}

        {risk.regulatory_flags.length > 0 && (
          <div>
            <div className="t-label" style={{ marginBottom: 6 }}>Regulatory reportability</div>
            <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
              {risk.regulatory_flags.map((flag) => (
                <span key={flag} className="chip chip-critical"
                  title={risk.flag_definitions?.[flag] ?? ''}>
                  <Icon name="alert" size={10} />{FLAG_LABEL[flag] ?? flag}
                </span>
              ))}
            </div>
            {risk.flag_definitions && (
              <ul style={{ marginTop: 8, display: 'grid', gap: 5 }}>
                {risk.regulatory_flags.map((flag) => (
                  <li key={flag} className="t-xs t-muted" style={{ lineHeight: 1.5 }}>
                    <b style={{ color: 'var(--ink-2)' }}>{FLAG_LABEL[flag] ?? flag}:</b>{' '}
                    {risk.flag_definitions?.[flag]}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/* ── 2. Completeness ───────────────────────────────────────────────────────── */
function CompletenessCard() {
  const { gaps, questions, completeness, phase } = useAppSelector((s) => s.intake)
  if (phase === 'idle') return null

  return (
    <div className="card">
      <div className="card-head">
        <Icon name="check" size={15} style={{ color: 'var(--accent)' }} />
        <span className="t-label grow">Completeness Checker</span>
        <span className="t-mono t-sm" style={{ fontWeight: 600 }}>{completeness.toFixed(0)}%</span>
      </div>
      <div className="card-body">
        {gaps.length === 0 ? (
          <Callout tone="accent" icon="check">
            The record satisfies the minimum content required by 21 CFR 211.198(a).
          </Callout>
        ) : (
          <>
            <div className="t-label" style={{ marginBottom: 4 }}>Missing information</div>
            {gaps.map((gap) => (
              <div className="gap-row" key={gap.field}>
                <span className={`gap-mark is-${gap.severity}`} />
                <div className="grow">
                  <div className="row" style={{ gap: 6 }}>
                    <b className="t-sm">{gap.label}</b>
                    <span className="t-xs t-muted" style={{ textTransform: 'uppercase', letterSpacing: '.06em' }}>
                      {gap.severity}
                    </span>
                  </div>
                  <div className="t-xs t-muted" style={{ marginTop: 2, lineHeight: 1.5 }}>{gap.reason}</div>
                </div>
              </div>
            ))}
          </>
        )}

        {questions.length > 0 && (
          <div style={{ marginTop: 'var(--sp-4)' }}>
            <div className="t-label" style={{ marginBottom: 6 }}>Suggested questions for the complainant</div>
            <ol style={{ display: 'grid', gap: 6 }}>
              {questions.map((question, index) => (
                <li key={index} className="t-sm" style={{
                  display: 'flex', gap: 8, padding: '7px 9px',
                  background: 'var(--surface-sunken)', borderRadius: 'var(--r-xs)',
                }}>
                  <span className="t-mono t-xs t-muted">{index + 1}.</span>
                  <span className="grow">{question}</span>
                  <button className="btn btn-ghost btn-sm" title="Copy"
                    onClick={() => navigator.clipboard?.writeText(question)}>
                    <Icon name="copy" size={11} />
                  </button>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </div>
  )
}

/* ── 3. Duplicates ─────────────────────────────────────────────────────────── */
function DuplicatesCard() {
  const dispatch = useAppDispatch()
  const navigate = useNavigate()
  const { duplicates, dismissedDuplicates } = useAppSelector((s) => s.intake)
  const visible = duplicates.filter((d) => !dismissedDuplicates.includes(d.complaint_id))
  if (!duplicates.length) return null

  return (
    <div className="card">
      <div className="card-head">
        <Icon name="duplicate" size={15} style={{ color: 'var(--major)' }} />
        <span className="t-label grow">Duplicate & Recurrence Detection</span>
        <span className="chip">{visible.length} match{visible.length === 1 ? '' : 'es'}</span>
      </div>
      <div className="card-body" style={{ display: 'grid', gap: 8 }}>
        {visible.length === 0 ? (
          <Callout icon="check">All candidates reviewed and dismissed.</Callout>
        ) : (
          visible.map((candidate) => (
            <div key={candidate.complaint_id} className="dup-card">
              <div className="row-between" style={{ marginBottom: 5 }}>
                <span className="t-mono t-sm" style={{ fontWeight: 600 }}>{candidate.reference}</span>
                <span className="row" style={{ gap: 6 }}>
                  <SeverityChip value={candidate.severity} />
                  <span className="dup-score" style={{
                    color: candidate.score >= 0.85 ? 'var(--critical)' : 'var(--major)',
                  }}>
                    {Math.round(candidate.score * 100)}%
                  </span>
                </span>
              </div>
              <div className="t-sm">{candidate.product_name}</div>
              <div className="t-xs t-muted" style={{ marginTop: 2 }}>
                Batch <span className="t-mono">{candidate.batch_number ?? '—'}</span> ·{' '}
                {candidate.complaint_type ?? '—'}
              </div>
              {candidate.rationale && (
                <div className="t-xs" style={{ marginTop: 6, color: 'var(--ink-2)' }}>
                  {candidate.rationale}
                </div>
              )}
              <div className="row" style={{ marginTop: 9, gap: 6 }}>
                <button className="btn btn-sm" onClick={() => navigate(`/register/${candidate.complaint_id}`)}>
                  <Icon name="link" size={11} /> Open record
                </button>
                <button className="btn btn-ghost btn-sm"
                  onClick={() => dispatch(dismissDuplicate(candidate.complaint_id))}>
                  Not a duplicate
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

/* ── 4. Root cause ─────────────────────────────────────────────────────────── */
function RootCauseCard() {
  const rootCauses = useAppSelector((s) => s.intake.rootCauses)
  if (!rootCauses.length) return null

  return (
    <div className="card">
      <div className="card-head">
        <Icon name="flask" size={15} style={{ color: 'var(--accent)' }} />
        <span className="t-label grow">Root Cause Hypotheses</span>
      </div>
      <div className="card-body">
        <p className="t-xs t-muted" style={{ marginBottom: 8, lineHeight: 1.5 }}>
          A starting point for the investigator, not a conclusion. Each hypothesis names the
          record or test that would confirm or eliminate it.
        </p>
        {rootCauses.map((cause, index) => (
          <div className="rca" key={index}>
            <div className="rca-head">
              <span className="rca-cat grow">{cause.category}</span>
              <span className="rca-bar"><i style={{ width: `${cause.likelihood * 100}%` }} /></span>
              <span className="rca-like">{Math.round(cause.likelihood * 100)}%</span>
            </div>
            <div className="t-sm" style={{ marginTop: 6 }}>{cause.hypothesis}</div>
            {cause.investigation_step && (
              <div className="rca-step">
                <b style={{ color: 'var(--ink)' }}>Next step · </b>{cause.investigation_step}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── 5. CAPA ───────────────────────────────────────────────────────────────── */
function CapaCard() {
  const capa = useAppSelector((s) => s.intake.capa)
  if (!capa.length) return null

  return (
    <div className="card">
      <div className="card-head">
        <Icon name="shield" size={15} style={{ color: 'var(--accent)' }} />
        <span className="t-label grow">CAPA Recommendation</span>
      </div>
      <div className="card-body">
        {capa.map((action, index) => (
          <div className="capa" key={index}>
            <span className={`capa-type is-${action.type}`}>{action.type}</span>
            <div>
              <div className="t-sm">{action.action}</div>
              <div className="capa-meta">
                {action.owner_function && <span><b>Owner:</b> {action.owner_function}</span>}
                {action.due_in_days && <span><b>Due:</b> +{action.due_in_days} days</span>}
              </div>
              {action.effectiveness_check && (
                <div className="rca-step" style={{ marginTop: 7 }}>
                  <b style={{ color: 'var(--ink)' }}>Effectiveness check · </b>
                  {action.effectiveness_check}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── 6. Summary ────────────────────────────────────────────────────────────── */
function SummaryCard() {
  const dispatch = useAppDispatch()
  const { summary, form } = useAppSelector((s) => s.intake)
  if (!summary) return null

  return (
    <div className="card">
      <div className="card-head">
        <Icon name="file" size={15} style={{ color: 'var(--accent)' }} />
        <span className="t-label grow">Complaint Summary</span>
        <button className="btn btn-ghost btn-sm" onClick={() => navigator.clipboard?.writeText(summary)}>
          <Icon name="copy" size={12} /> Copy
        </button>
      </div>
      <div className="card-body">
        <p style={{ lineHeight: 1.65, color: 'var(--ink)' }}>{summary}</p>
        {!form.description && (
          <button className="btn btn-sm" style={{ marginTop: 'var(--sp-3)' }}
            onClick={() => dispatch(fieldChanged({ field: 'description', value: summary }))}>
            <Icon name="arrow" size={12} /> Use as complaint description
          </button>
        )}
      </div>
    </div>
  )
}

export function RiskAssessment() {
  const phase = useAppSelector((s) => s.intake.phase)
  const risk = useAppSelector((s) => s.intake.risk)
  if (phase === 'idle' || !risk) return null

  return (
    <section className="assessment" id="assessment">
      <div className="row" style={{ gap: 10 }}>
        <h2 className="t-title">AI Copilot Assessment</h2>
        <span className="hairline grow" />
        <span className="t-xs t-muted">Advisory only · a qualified reviewer approves every decision</span>
      </div>
      <div className="assess-grid">
        <div style={{ display: 'grid', gap: 'var(--sp-4)' }}>
          <RiskCard />
          <SummaryCard />
        </div>
        <div style={{ display: 'grid', gap: 'var(--sp-4)' }}>
          <CompletenessCard />
          <DuplicatesCard />
        </div>
        <div style={{ display: 'grid', gap: 'var(--sp-4)' }}>
          <RootCauseCard />
          <CapaCard />
        </div>
      </div>
    </section>
  )
}
