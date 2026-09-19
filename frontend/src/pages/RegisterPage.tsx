import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAppDispatch, useAppSelector } from '@/app/store'
import {
  fetchComplaints, filterChanged, filtersCleared, toggleFacet,
} from '@/features/complaints/complaintsSlice'
import { Icon } from '@/components/Icon'
import { Empty, SeverityChip } from '@/components/ui/primitives'
import '@/components/register/register.css'

const fmt = (value?: string | null) =>
  value ? new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: '2-digit' }) : '—'

export function RegisterPage() {
  const dispatch = useAppDispatch()
  const navigate = useNavigate()
  const { items, total, filters, listStatus } = useAppSelector((s) => s.complaints)
  const taxonomy = useAppSelector((s) => s.system.taxonomy)

  const [search] = useSearchParams()
  const linkedQuery = search.get('q')
  useEffect(() => {
    if (linkedQuery) dispatch(filterChanged({ q: linkedQuery }))
  }, [linkedQuery, dispatch])

  useEffect(() => { dispatch(fetchComplaints()) }, [dispatch, filters])

  const sortBy = (column: string) => {
    const desc = filters.sort === column
    dispatch(filterChanged({ sort: desc ? `-${column}` : column }))
  }
  const caret = (column: string) =>
    filters.sort === column ? ' ↑' : filters.sort === `-${column}` ? ' ↓' : ''

  const pages = Math.max(1, Math.ceil(total / filters.page_size))
  const hasFilters = Boolean(filters.q || filters.severity.length || filters.status.length)
  const today = new Date().toISOString().slice(0, 10)

  return (
    <div className="register">
      <div className="row-between">
        <div>
          <h1 className="t-display">Complaint Register</h1>
          <p className="t-sm t-muted" style={{ marginTop: 3 }}>
            Every market complaint logged against API and finished-dosage-form product.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => navigate('/intake')}>
          <Icon name="plus" size={14} /> New complaint
        </button>
      </div>

      <div className="card">
        <div className="filters">
          <div className="search-box">
            <Icon name="search" size={14} />
            <input
              className="input" placeholder="Search reference, product, batch, customer…"
              value={filters.q}
              onChange={(e) => dispatch(filterChanged({ q: e.target.value }))}
            />
          </div>

          <span className="t-label">Severity</span>
          {(taxonomy?.severities ?? []).map((severity) => (
            <button
              key={severity}
              className={`facet${filters.severity.includes(severity) ? ' is-on' : ''}`}
              onClick={() => dispatch(toggleFacet({ key: 'severity', value: severity }))}
            >
              {severity}
            </button>
          ))}

          <span className="t-label" style={{ marginLeft: 6 }}>Status</span>
          {['Pending Triage', 'Under Investigation', 'CAPA Initiated', 'Closed'].map((status) => (
            <button
              key={status}
              className={`facet${filters.status.includes(status) ? ' is-on' : ''}`}
              onClick={() => dispatch(toggleFacet({ key: 'status', value: status }))}
            >
              {status}
            </button>
          ))}

          {hasFilters && (
            <button className="btn btn-ghost btn-sm" onClick={() => dispatch(filtersCleared())}>
              <Icon name="close" size={11} /> Clear
            </button>
          )}
        </div>

        <div className="table-wrap">
          {listStatus === 'loading' && !items.length ? (
            <div style={{ padding: 'var(--sp-5)', display: 'grid', gap: 8 }}>
              {[...Array(6)].map((_, i) => <div key={i} className="skeleton" style={{ height: 38 }} />)}
            </div>
          ) : items.length === 0 ? (
            <Empty icon="register" title="No complaints match these filters">
              Adjust the search or clear the facets to see the full register.
            </Empty>
          ) : (
            <table className="reg">
              <thead>
                <tr>
                  <th className="sortable" onClick={() => sortBy('reference')}>
                    Reference{caret('reference')}
                  </th>
                  <th className="sortable" onClick={() => sortBy('product_name')}>
                    Product / Batch{caret('product_name')}
                  </th>
                  <th>Defect</th>
                  <th className="sortable" onClick={() => sortBy('severity')}>
                    Severity{caret('severity')}
                  </th>
                  <th className="sortable" onClick={() => sortBy('ai_risk_score')}>
                    Risk{caret('ai_risk_score')}
                  </th>
                  <th>Status</th>
                  <th className="sortable" onClick={() => sortBy('date_received')}>
                    Received{caret('date_received')}
                  </th>
                  <th className="sortable" onClick={() => sortBy('due_date')}>
                    Due{caret('due_date')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((complaint) => {
                  const overdue = complaint.due_date && complaint.due_date < today
                    && complaint.status !== 'Closed'
                  return (
                    <tr key={complaint.id} onClick={() => navigate(`/register/${complaint.id}`)}>
                      <td>
                        <div className="cell-ref">{complaint.reference}</div>
                        <div className="cell-sub">{complaint.customer_name ?? '—'}</div>
                      </td>
                      <td>
                        <div>{complaint.product_name ?? '—'}</div>
                        <div className="cell-sub t-mono">{complaint.batch_number ?? '—'}</div>
                      </td>
                      <td style={{ maxWidth: 200 }}>{complaint.complaint_type ?? '—'}</td>
                      <td><SeverityChip value={complaint.severity} /></td>
                      <td className="t-mono">
                        {complaint.ai_risk_score != null ? complaint.ai_risk_score.toFixed(0) : '—'}
                      </td>
                      <td><span className="chip">{complaint.status}</span></td>
                      <td className="t-mono t-xs">{fmt(complaint.date_received)}</td>
                      <td className={`t-mono t-xs${overdue ? ' overdue' : ''}`}>
                        {fmt(complaint.due_date)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        <div className="pager">
          <span className="t-xs t-muted">
            {total} record{total === 1 ? '' : 's'} · page {filters.page} of {pages}
          </span>
          <div className="row">
            <button className="btn btn-sm" disabled={filters.page <= 1}
              onClick={() => dispatch(filterChanged({ page: filters.page - 1 }))}>
              Previous
            </button>
            <button className="btn btn-sm" disabled={filters.page >= pages}
              onClick={() => dispatch(filterChanged({ page: filters.page + 1 }))}>
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
