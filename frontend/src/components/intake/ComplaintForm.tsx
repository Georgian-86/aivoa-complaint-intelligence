import { useEffect, useMemo } from 'react'
import { useAppDispatch, useAppSelector } from '@/app/store'
import { fieldChanged, landingCleared, resetIntake, saveComplaint } from '@/features/intake/intakeSlice'
import { notify } from '@/features/system/systemSlice'
import { ConfidenceBadge } from '../ui/ConfidenceBadge'
import { Icon } from '../Icon'
import './intake.css'

interface FieldProps {
  name: string
  label: string
  required?: boolean
  type?: 'text' | 'date' | 'number' | 'textarea' | 'select' | 'checkbox'
  options?: string[]
  placeholder?: string
  mono?: boolean
  span?: boolean
  suffix?: string
}

const AWAITING = 'Awaiting AI extraction…'

/** One controlled field, carrying its own provenance badge. */
function Field({
  name, label, required, type = 'text', options, placeholder, mono, span, suffix,
}: FieldProps) {
  const dispatch = useAppDispatch()
  const value = useAppSelector((s) => s.intake.form[name])
  const meta = useAppSelector((s) => s.intake.fields[name])
  const isLanding = useAppSelector((s) => s.intake.landed.includes(name))
  const running = useAppSelector((s) => s.intake.phase === 'running')
  // Read unconditionally: the paired unit input is only rendered for the
  // quantity field, but a hook may never live inside a branch.
  const unit = useAppSelector((s) => s.intake.form.quantity_unit)

  const tone = meta && meta.source !== 'none' && meta.source !== 'analyst'
    ? (meta.confidence < 0.5 ? ' is-low' : ' is-ai') : ''
  const className = `${type === 'textarea' ? 'textarea' : type === 'select' ? 'select' : 'input'}`
    + `${tone}${mono ? ' is-mono' : ''}${isLanding ? ' is-landing' : ''}`

  const onChange = (next: unknown) => dispatch(fieldChanged({ field: name, value: next }))
  const id = `f-${name}`

  return (
    <div className={`field${span ? ' span-2' : ''}`}>
      <label className="field-label" htmlFor={id}>
        <span>{label}{required && <span className="req">*</span>}</span>
        {meta && <ConfidenceBadge field={meta} />}
      </label>

      {type === 'textarea' ? (
        <textarea
          id={id} className={className} rows={4}
          placeholder={placeholder ?? (running ? AWAITING : 'Describe the reported defect…')}
          value={(value as string) ?? ''} onChange={(e) => onChange(e.target.value)}
        />
      ) : type === 'select' ? (
        <select
          id={id} className={className} value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">{running ? AWAITING : 'Select…'}</option>
          {options?.map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
      ) : type === 'checkbox' ? (
        <div className="row" style={{ height: 34 }}>
          <input
            id={id} type="checkbox" checked={Boolean(value)}
            onChange={(e) => onChange(e.target.checked)}
            style={{ width: 15, height: 15, accentColor: 'var(--accent)' }}
          />
          <label htmlFor={id} className="t-sm t-muted" style={{ cursor: 'pointer' }}>
            {value ? 'Sample available for testing' : 'No sample available'}
          </label>
        </div>
      ) : suffix ? (
        <div className="qty-group">
          <input
            id={id} className={className} type={type}
            placeholder={placeholder ?? (running ? AWAITING : '')}
            value={(value as string) ?? ''} onChange={(e) => onChange(e.target.value)}
          />
          <input
            className="input" aria-label="Unit"
            value={(unit as string) ?? ''}
            onChange={(e) => dispatch(fieldChanged({ field: 'quantity_unit', value: e.target.value }))}
          />
        </div>
      ) : (
        <input
          id={id} className={className} type={type}
          placeholder={placeholder ?? (running ? AWAITING : '')}
          value={(value as string) ?? ''} onChange={(e) => onChange(e.target.value)}
        />
      )}
    </div>
  )
}

function Section({ no, title, children }: { no: number; title: string; children: React.ReactNode }) {
  return (
    <section className="section">
      <div className="section-gutter">
        <span className="section-no">{no}</span>
        <span className="section-rule" />
      </div>
      <div>
        <h3 className="section-title">{title}</h3>
        <div className="section-fields">{children}</div>
      </div>
    </section>
  )
}

export function ComplaintForm() {
  const dispatch = useAppDispatch()
  const taxonomy = useAppSelector((s) => s.system.taxonomy)
  const { saving, savedReference, phase, form, completeness, gaps } = useAppSelector((s) => s.intake)
  const landed = useAppSelector((s) => s.intake.landed)

  // The landing flash is a one-shot cue, not a persistent state.
  useEffect(() => {
    if (!landed.length) return
    const timer = setTimeout(() => dispatch(landingCleared()), 1000)
    return () => clearTimeout(timer)
  }, [landed, dispatch])

  const blockers = useMemo(() => gaps.filter((g) => g.severity === 'blocker'), [gaps])
  const canSave = Boolean(form.product_name && form.batch_number && form.description)

  const onSave = async () => {
    const action = await dispatch(saveComplaint())
    if (saveComplaint.fulfilled.match(action)) {
      dispatch(notify({ tone: 'ok', message: `Complaint ${action.payload.reference} logged to the register.` }))
    } else {
      dispatch(notify({ tone: 'error', message: 'Could not save the complaint. Check the API is running.' }))
    }
  }

  return (
    <div className="card">
      <div className="card-head">
        <div className="grow">
          <h2 className="t-title">Log Customer Complaint</h2>
          <p className="t-xs t-muted" style={{ marginTop: 2 }}>
            API &amp; FDF Quality Assurance Module · 21 CFR 211.198
          </p>
        </div>
        {savedReference ? (
          <span className="chip chip-positive t-mono"><Icon name="check" size={11} />{savedReference}</span>
        ) : (
          <span className="chip chip-major"><span className="dot" />{form.status || 'Pending Triage'}</span>
        )}
      </div>

      <div className="card-body">
        {phase === 'complete' && completeness > 0 && (
          <div className="row-between" style={{ marginBottom: 'var(--sp-5)' }}>
            <div className="grow">
              <div className="row-between" style={{ marginBottom: 5 }}>
                <span className="t-label">Record completeness</span>
                <span className="t-mono t-sm" style={{ fontWeight: 600 }}>
                  {completeness.toFixed(0)}%
                  {blockers.length > 0 && (
                    <span style={{ color: 'var(--critical)', fontWeight: 500 }}>
                      {' '}· {blockers.length} blocker{blockers.length > 1 ? 's' : ''}
                    </span>
                  )}
                </span>
              </div>
              <div className="meter">
                <i style={{
                  width: `${completeness}%`,
                  background: completeness >= 90 ? 'var(--positive)'
                    : completeness >= 70 ? 'var(--accent)' : 'var(--major)',
                }} />
              </div>
            </div>
          </div>
        )}

        <Section no={1} title="Origin & Customer Details">
          <Field name="complaint_source" label="Complaint Source" required
            type="select" options={taxonomy?.complaint_sources} />
          <Field name="customer_name" label="Customer Name" required />
          <Field name="customer_contact" label="Contact (e-mail / phone)" />
          <Field name="customer_country" label="Country of Origin" />
        </Section>

        <Section no={2} title="Product & Batch Identification">
          <Field name="product_name" label="Product Name" required />
          <Field name="product_strength" label="Product Strength / Grade" required />
          <Field name="dosage_form" label="Dosage Form" type="select" options={taxonomy?.dosage_forms} />
          <Field name="batch_number" label="Batch / Lot Number" required mono />
          <Field name="manufacturing_date" label="Manufacturing Date" type="date" />
          <Field name="expiry_date" label="Expiry / Retest Date" type="date" required />
          <Field name="quantity_affected" label="Quantity Affected" type="number" suffix="unit" />
          <Field name="market_country" label="Market / Destination" />
        </Section>

        <Section no={3} title="Complaint Details">
          <Field name="complaint_type" label="Complaint Type" required
            type="select" options={taxonomy?.complaint_types} />
          <Field name="complaint_date" label="Complaint Date" type="date" required />
          <Field name="date_received" label="Date Received by QA" type="date" />
          <Field name="sample_available" label="Sample Availability" type="checkbox" />
          <Field name="description" label="Detailed Complaint Description" required
            type="textarea" span />
        </Section>

        <Section no={4} title="Initial Assessment & Priority">
          <Field name="severity" label="Initial Severity (GMP)" required
            type="select" options={taxonomy?.severities} />
          <Field name="priority" label="Priority" type="select" options={taxonomy?.priorities} />
          <Field name="status" label="Record Status" type="select" options={taxonomy?.statuses} />
          <Field name="due_date" label="Investigation Due" type="date" />
        </Section>
      </div>

      <div className="form-actions">
        <button className="btn" onClick={() => dispatch(resetIntake())}>
          <Icon name="reset" size={14} /> Reset Form
        </button>
        <div className="row">
          {!canSave && (
            <span className="t-xs t-muted">Product, batch and description are required</span>
          )}
          <button className="btn btn-primary" onClick={onSave} disabled={saving || !canSave}>
            <Icon name="save" size={14} />
            {saving ? 'Saving…' : 'Save Complaint'}
          </button>
        </div>
      </div>
    </div>
  )
}
