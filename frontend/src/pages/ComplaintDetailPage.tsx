import { useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useAppDispatch, useAppSelector } from '@/app/store'
import { changeStatus, detailCleared, fetchComplaint } from '@/features/complaints/complaintsSlice'
import { notify } from '@/features/system/systemSlice'
import { Icon } from '@/components/Icon'
import { Callout, Empty, RiskMeter, SeverityChip } from '@/components/ui/primitives'
import type { CapaAction, RootCauseHypothesis } from '@/api/types'
import '@/components/register/register.css'
import '@/components/intake/intake.css'

const dt = (value?: string | null) =>
  value ? new Date(value).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }) : '—'

const d = (value?: string | null) =>
  value ? new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="kv"><dt>{label}</dt><dd>{children ?? '—'}</dd></div>
}

export function ComplaintDetailPage() {
  const { id = '' } = useParams()
  const dispatch = useAppDispatch()
  const navigate = useNavigate()
  const { detail, detailStatus } = useAppSelector((s) => s.complaints)
  const taxonomy = useAppSelector((s) => s.system.taxonomy)

  useEffect(() => {
    dispatch(fetchComplaint(id))
    return () => { dispatch(detailCleared()) }
  }, [dispatch, id])

  if (detailStatus === 'loading' || !detail) {
    return detailStatus === 'error'
      ? <Empty icon="alert" title="Complaint not found">This record may have been deleted.</Empty>
      : <div style={{ display: 'grid', gap: 12 }}>
          {[...Array(4)].map((_, i) => <div key={i} className="skeleton" style={{ height: 90 }} />)}
        </div>
  }

  const payload = (detail.ai_payload ?? {}) as {
    risk?: { drivers?: { factor: string; weight: number }[]; rationale?: string; regulatory_flags?: string[] }
    root_causes?: RootCauseHypothesis[]
    capa?: CapaAction[]
    completeness_score?: number
  }
  const run = detail.agent_runs?.[detail.agent_runs.length - 1]

  return (
    <div className="detail">
      <div className="row-between">
        <div>
          <button className="btn btn-ghost btn-sm" onClick={() => navigate('/register')}
            style={{ marginBottom: 6 }}>
            <Icon name="chevron" size={11} style={{ transform: 'rotate(180deg)' }} /> Register
          </button>
          <h1 className="t-display t-mono">{detail.reference}</h1>
          <p className="t-sm t-muted" style={{ marginTop: 3 }}>
            {detail.product_name} · batch <span className="t-mono">{detail.batch_number}</span>
          </p>
        </div>
        <div className="row">
          <SeverityChip value={detail.severity} />
          <select
            className="select" style={{ width: 210 }} value={detail.status ?? ''}
            onChange={async (e) => {
              const action = await dispatch(changeStatus({ id, status: e.target.value }))
              if (changeStatus.fulfilled.match(action)) {
                dispatch(notify({ tone: 'ok', message: `Status set to ${e.target.value}.` }))
              }
            }}
          >
            {(taxonomy?.statuses ?? []).map((status) => (
              <option key={status} value={status}>{status}</option>
            ))}
          </select>
        </div>
      </div>

      <dl className="doc-strip">
        <div className="doc-cell"><dt>Received</dt><dd>{d(detail.date_received)}</dd></div>
        <div className="doc-cell"><dt>Due</dt><dd>{d(detail.due_date)}</dd></div>
        <div className="doc-cell"><dt>Priority</dt><dd>{detail.priority ?? '—'}</dd></div>
        <div className="doc-cell"><dt>Risk</dt>
          <dd className="t-mono">{detail.ai_risk_score?.toFixed(0) ?? '—'} · {detail.ai_risk_band ?? '—'}</dd></div>
        <div className="doc-cell"><dt>Channel</dt><dd>{detail.intake_channel}</dd></div>
        <div className="doc-cell"><dt>Logged by</dt><dd>{detail.created_by}</dd></div>
      </dl>

      <div className="detail-grid">
        <div style={{ display: 'grid', gap: 'var(--sp-4)' }}>
          {detail.ai_summary && (
            <div className="card">
              <div className="card-head">
                <Icon name="sparkle" size={14} style={{ color: 'var(--accent)' }} />
                <span className="t-label grow">AI summary</span>
              </div>
              <div className="card-body"><p style={{ lineHeight: 1.65 }}>{detail.ai_summary}</p></div>
            </div>
          )}

          <div className="card">
            <div className="card-head"><span className="t-label grow">Complaint record</span></div>
            <div className="card-body">
              <Row label="Complaint source">{detail.complaint_source}</Row>
              <Row label="Customer">{detail.customer_name}</Row>
              <Row label="Contact">{detail.customer_contact}</Row>
              <Row label="Country">{detail.customer_country ?? detail.market_country}</Row>
              <Row label="Product">{detail.product_name}</Row>
              <Row label="Strength / grade">{detail.product_strength}</Row>
              <Row label="Dosage form">{detail.dosage_form}</Row>
              <Row label="Batch / lot"><span className="t-mono">{detail.batch_number}</span></Row>
              <Row label="Manufactured">{d(detail.manufacturing_date)}</Row>
              <Row label="Expiry / retest">{d(detail.expiry_date)}</Row>
              <Row label="Quantity affected">
                {detail.quantity_affected != null
                  ? `${detail.quantity_affected} ${detail.quantity_unit ?? ''}` : null}
              </Row>
              <Row label="Complaint type">{detail.complaint_type}</Row>
              <Row label="Sample available">
                {detail.sample_available == null ? null : detail.sample_available ? 'Yes' : 'No'}
              </Row>
              <Row label="Description">
                <span style={{ lineHeight: 1.6 }}>{detail.description}</span>
              </Row>
            </div>
          </div>

          {payload.root_causes && payload.root_causes.length > 0 && (
            <div className="card">
              <div className="card-head">
                <Icon name="flask" size={14} style={{ color: 'var(--accent)' }} />
                <span className="t-label grow">Root cause hypotheses at intake</span>
              </div>
              <div className="card-body">
                {payload.root_causes.map((cause, index) => (
                  <div className="rca" key={index}>
                    <div className="rca-head">
                      <span className="rca-cat">{cause.category}</span>
                      <span className="rca-like">{Math.round(cause.likelihood * 100)}%</span>
                    </div>
                    <div className="t-sm" style={{ marginTop: 4 }}>{cause.hypothesis}</div>
                    {cause.investigation_step && (
                      <div className="rca-step"><b>Next step · </b>{cause.investigation_step}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {payload.capa && payload.capa.length > 0 && (
            <div className="card">
              <div className="card-head">
                <Icon name="shield" size={14} style={{ color: 'var(--accent)' }} />
                <span className="t-label grow">Recommended CAPA</span>
              </div>
              <div className="card-body">
                {payload.capa.map((action, index) => (
                  <div className="capa" key={index}>
                    <span className={`capa-type is-${action.type}`}>{action.type}</span>
                    <div>
                      <div className="t-sm">{action.action}</div>
                      <div className="capa-meta">
                        {action.owner_function && <span><b>Owner:</b> {action.owner_function}</span>}
                        {action.due_in_days && <span><b>Due:</b> +{action.due_in_days} days</span>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div style={{ display: 'grid', gap: 'var(--sp-4)' }}>
          {detail.ai_risk_score != null && (
            <div className="card">
              <div className="card-head">
                <Icon name="shield" size={14} />
                <span className="t-label grow">Risk at intake</span>
              </div>
              <div className="card-body" style={{ display: 'grid', gap: 'var(--sp-3)' }}>
                <RiskMeter score={detail.ai_risk_score} band={detail.ai_risk_band ?? 'Low'} />
                {payload.risk?.rationale && (
                  <p className="t-sm" style={{ color: 'var(--ink-2)', lineHeight: 1.6 }}>
                    {payload.risk.rationale}
                  </p>
                )}
                {payload.risk?.drivers?.map((driver, index) => (
                  <div className="driver" key={index}>
                    <div className="driver-head">
                      <span className="t-sm">{driver.factor}</span>
                      <span className="driver-w">{driver.weight?.toFixed(2)}</span>
                    </div>
                    <div className="driver-bar">
                      <i style={{
                        width: `${(driver.weight ?? 0) * 100}%`,
                        background: 'var(--band-high)',
                      }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {run && (
            <div className="card">
              <div className="card-head">
                <Icon name="trace" size={14} style={{ color: 'var(--accent)' }} />
                <span className="t-label grow">Agent trace</span>
                <span className="t-mono t-xs t-muted">{run.duration_ms ?? 0} ms</span>
              </div>
              <div className="card-body">
                <div className="t-xs t-muted" style={{ marginBottom: 8, lineHeight: 1.5 }}>
                  Engine <b>{run.engine}</b>
                  {run.model_extraction && <> · extraction <span className="t-mono">{run.model_extraction}</span></>}
                  {run.model_reasoning && <> · reasoning <span className="t-mono">{run.model_reasoning}</span></>}
                </div>
                <div className="agent-rail">
                  {run.traces.map((trace) => (
                    <div key={trace.node} className={`agent-step is-${trace.status === 'error' ? 'error' : 'ok'}`}>
                      <span className="agent-node">
                        <Icon name={trace.status === 'error' ? 'close' : 'check'} size={9} strokeWidth={2.6} />
                      </span>
                      <div>
                        <div className="agent-label">{trace.label}</div>
                        {trace.note && <div className="agent-detail">{trace.note}</div>}
                      </div>
                      <span className="agent-ms">{trace.duration_ms} ms</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          <div className="card">
            <div className="card-head">
              <Icon name="clock" size={14} />
              <span className="t-label grow">Audit trail</span>
            </div>
            <div className="card-body">
              <Callout icon="shield">
                Append-only record of every change, attributable to a named actor — ALCOA+ and
                21 CFR Part 11 expectations.
              </Callout>
              <div className="audit" style={{ marginTop: 'var(--sp-3)' }}>
                {detail.audit_events.map((event) => (
                  <div key={event.id} className={`audit-item${event.actor_type === 'agent' ? ' is-agent' : ''}`}>
                    <div className="row-between">
                      <b className="t-sm">{event.action.replace(/_/g, ' ')}</b>
                      <span className="audit-when">{dt(event.created_at)}</span>
                    </div>
                    <div className="t-xs t-muted" style={{ marginTop: 2 }}>
                      {event.actor} {event.detail && `· ${event.detail}`}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {detail.source_text && (
            <div className="card">
              <div className="card-head">
                <Icon name="file" size={14} />
                <span className="t-label grow">Source document</span>
              </div>
              <div className="card-body">
                <div className="t-xs t-muted" style={{ marginBottom: 6 }}>
                  {detail.source_document_name ?? 'Pasted text'}
                </div>
                <pre style={{
                  margin: 0, maxHeight: 260, overflow: 'auto', whiteSpace: 'pre-wrap',
                  fontFamily: 'var(--font-mono)', fontSize: 11, lineHeight: 1.6,
                  color: 'var(--ink-2)', background: 'var(--surface-sunken)',
                  padding: 11, borderRadius: 'var(--r-sm)',
                }}>{detail.source_text}</pre>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
