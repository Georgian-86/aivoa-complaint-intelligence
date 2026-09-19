import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppDispatch, useAppSelector } from '@/app/store'
import { fetchAnalytics } from '@/features/complaints/complaintsSlice'
import { Icon } from '@/components/Icon'
import { Empty, SeverityChip, Stat } from '@/components/ui/primitives'
import '@/components/register/register.css'

const SEV_COLOR: Record<string, string> = {
  Critical: 'var(--critical)', Major: 'var(--major)',
  Minor: 'var(--minor)', Unclassified: 'var(--line-strong)',
}

/** Monthly intake volume as a plain column chart — no chart library, so the
 *  marks inherit the product's own palette rather than a vendor's. */
function VolumeChart({ data }: { data: { month: string; count: number }[] }) {
  if (!data.length) return <Empty icon="dashboard" title="No intake history yet" />

  // Pad to a rolling twelve months so the chart reads as a time series rather
  // than as three isolated columns — a gap is information in trend review.
  const series: { month: string; count: number }[] = []
  const counts = new Map(data.map((d) => [d.month, d.count]))
  const cursor = new Date()
  cursor.setDate(1)
  for (let i = 11; i >= 0; i -= 1) {
    const d = new Date(cursor.getFullYear(), cursor.getMonth() - i, 1)
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    series.push({ month: key, count: counts.get(key) ?? 0 })
  }

  const max = Math.max(...series.map((d) => d.count), 1)
  const W = 100 / series.length

  return (
    <div>
      <svg viewBox="0 0 100 44" preserveAspectRatio="none" style={{ width: '100%', height: 150 }}
        role="img" aria-label="Complaints logged per month">
        {[0, 11, 22, 33, 44].map((y) => (
          <line key={y} x1="0" y1={y} x2="100" y2={y} stroke="var(--line-soft)" strokeWidth=".4"
            vectorEffect="non-scaling-stroke" />
        ))}
        {series.map((point, index) => {
          const h = (point.count / max) * 40
          return (
            <rect
              key={point.month} x={index * W + W * 0.3} y={44 - h}
              width={W * 0.4} height={Math.max(h, 0.5)}
              fill={point.count ? 'var(--accent)' : 'var(--line)'} rx=".5"
            >
              <title>{point.month}: {point.count}</title>
            </rect>
          )
        })}
      </svg>
      <div style={{ display: 'flex', marginTop: 6 }}>
        {series.map((point) => (
          <span key={point.month} style={{
            flex: 1, textAlign: 'center', fontSize: 9.5, color: 'var(--ink-4)',
            fontFamily: 'var(--font-mono)',
          }}>
            {point.month.slice(5)}{point.month.endsWith('-01') ? `/${point.month.slice(2, 4)}` : ''}
          </span>
        ))}
      </div>
    </div>
  )
}

export function DashboardPage() {
  const dispatch = useAppDispatch()
  const navigate = useNavigate()
  const { analytics, analyticsStatus } = useAppSelector((s) => s.complaints)

  useEffect(() => { dispatch(fetchAnalytics()) }, [dispatch])

  if (analyticsStatus === 'loading' || !analytics) {
    return <div style={{ display: 'grid', gap: 12 }}>
      {[...Array(3)].map((_, i) => <div key={i} className="skeleton" style={{ height: 110 }} />)}
    </div>
  }

  const severityTotal = Object.values(analytics.by_severity).reduce((a, b) => a + b, 0) || 1
  const typeMax = Math.max(...analytics.by_type.map((t) => t.count), 1)

  return (
    <div className="dash">
      <div className="row-between">
        <div>
          <h1 className="t-display">Complaint Trend Dashboard</h1>
          <p className="t-sm t-muted" style={{ marginTop: 3 }}>
            Repeat minor events are a signal, not noise — trending is a GMP expectation, not a nicety.
          </p>
        </div>
        <button className="btn" onClick={() => navigate('/register')}>
          <Icon name="register" size={14} /> Open register
        </button>
      </div>

      <div className="stat-row">
        <Stat label="Total complaints" value={analytics.total} />
        <Stat label="Open" value={analytics.open_count}
          sub={`${Math.round((analytics.open_count / (analytics.total || 1)) * 100)}% of register`} />
        <Stat label="Past target TAT" value={analytics.overdue_count}
          tone={analytics.overdue_count ? 'var(--critical)' : undefined}
          sub="Investigation overdue" />
        <Stat label="Mean risk score"
          value={analytics.avg_risk_score?.toFixed(0) ?? '—'} sub="Composite, 0–100" />
        <Stat label="AI-assisted intake"
          value={`${Math.round(analytics.ai_assisted_share * 100)}%`}
          sub="Logged from a document or e-mail" />
      </div>

      <div className="chart-row">
        <div className="card">
          <div className="card-head"><span className="t-label grow">Intake volume by month</span></div>
          <div className="card-body"><VolumeChart data={analytics.by_month} /></div>
        </div>

        <div className="card">
          <div className="card-head"><span className="t-label grow">Severity distribution</span></div>
          <div className="card-body">
            <div className="bar-track" style={{ height: 26, marginBottom: 14 }}>
              {Object.entries(analytics.by_severity).filter(([, v]) => v > 0).map(([name, value]) => (
                <div key={name} className="bar-fill" title={`${name}: ${value}`}
                  style={{ width: `${(value / severityTotal) * 100}%`, background: SEV_COLOR[name] }} />
              ))}
            </div>
            {Object.entries(analytics.by_severity).map(([name, value]) => (
              <div className="bar-row" key={name}>
                <div className="row" style={{ gap: 7 }}>
                  <span className="dot" style={{ color: SEV_COLOR[name], width: 7, height: 7 }} />
                  <span className="t-sm">{name}</span>
                  <span className="t-xs t-muted">
                    {Math.round((value / severityTotal) * 100)}%
                  </span>
                </div>
                <span className="bar-num">{value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="chart-row">
        <div className="card">
          <div className="card-head"><span className="t-label grow">Top defect categories</span></div>
          <div className="card-body">
            {analytics.by_type.length === 0
              ? <Empty icon="dashboard" title="No classified complaints yet" />
              : analytics.by_type.map((row) => (
                <div className="bar-row" key={row.name}>
                  <div>
                    <div className="t-sm" style={{ marginBottom: 4 }}>{row.name}</div>
                    <div className="bar-track" style={{ height: 6 }}>
                      <div className="bar-fill" style={{
                        width: `${(row.count / typeMax) * 100}%`, background: 'var(--accent)',
                      }} />
                    </div>
                  </div>
                  <span className="bar-num">{row.count}</span>
                </div>
              ))}
          </div>
        </div>

        <div className="card">
          <div className="card-head"><span className="t-label grow">Workflow status</span></div>
          <div className="card-body">
            {Object.entries(analytics.by_status).map(([name, value]) => (
              <div className="bar-row" key={name}>
                <div>
                  <div className="t-sm" style={{ marginBottom: 4 }}>{name}</div>
                  <div className="bar-track" style={{ height: 6 }}>
                    <div className="bar-fill" style={{
                      width: `${(value / (analytics.total || 1)) * 100}%`,
                      background: name === 'Closed' ? 'var(--positive)' : 'var(--ink-3)',
                    }} />
                  </div>
                </div>
                <span className="bar-num">{value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <Icon name="duplicate" size={15} style={{ color: 'var(--major)' }} />
          <span className="t-label grow">Recurrence watchlist</span>
          <span className="t-xs t-muted">Same product, same defect, more than once</span>
        </div>
        <div className="card-body">
          {analytics.recurrence.length === 0 ? (
            <Empty icon="check" title="No recurring defect patterns">
              No product has attracted the same defect category more than once in the register.
            </Empty>
          ) : (
            <table className="reg">
              <thead>
                <tr>
                  <th>Product</th><th>Defect category</th><th>Events</th>
                  <th>Batches</th><th>Worst severity</th>
                </tr>
              </thead>
              <tbody>
                {analytics.recurrence.map((row) => (
                  <tr key={`${row.product_name}-${row.complaint_type}`}
                    onClick={() => navigate(`/register?q=${encodeURIComponent(row.product_name)}`)}>
                    <td>{row.product_name}</td>
                    <td>{row.complaint_type}</td>
                    <td className="t-mono">{row.count}</td>
                    <td className="t-mono t-xs">
                      {row.batches.join(', ') || '—'}
                      {row.batch_count > row.batches.length && ` +${row.batch_count - row.batches.length}`}
                    </td>
                    <td><SeverityChip value={row.worst_severity} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
