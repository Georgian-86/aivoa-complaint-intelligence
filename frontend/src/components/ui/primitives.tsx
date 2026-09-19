import type { ReactNode } from 'react'
import { Icon, type IconName } from '../Icon'
import './ui.css'

export function SeverityChip({ value, size }: { value?: string | null; size?: 'sm' }) {
  if (!value) return <span className="chip">Unclassified</span>
  const tone = value.toLowerCase()
  return (
    <span className={`chip chip-${tone}${size === 'sm' ? ' btn-sm' : ''}`}>
      <span className="dot" />{value}
    </span>
  )
}

const BANDS = ['Low', 'Moderate', 'High', 'Severe'] as const
const BAND_VAR: Record<string, string> = {
  Low: 'var(--band-low)', Moderate: 'var(--band-moderate)',
  High: 'var(--band-high)', Severe: 'var(--band-severe)',
}

/**
 * Segmented risk meter: four 25-point bands that fill proportionally.
 * A dial reads as decoration; a scale reads as a measurement.
 */
export function RiskMeter({ score, band }: { score: number; band: string }) {
  return (
    <div className="risk-meter">
      <div className="risk-scale" role="img" aria-label={`Risk score ${score} of 100, band ${band}`}>
        {BANDS.map((name, index) => {
          const lower = index * 25
          const fill = Math.max(0, Math.min(1, (score - lower) / 25))
          return (
            <div key={name} className="risk-seg">
              <i style={{ background: BAND_VAR[name], transform: `scaleX(${fill})` }} />
            </div>
          )
        })}
      </div>
      <div className="risk-ticks">
        {BANDS.map((name) => (
          <span key={name} style={{ color: band === name ? BAND_VAR[name] : undefined,
            fontWeight: band === name ? 700 : 400 }}>{name}</span>
        ))}
      </div>
    </div>
  )
}

export function Meter({ value, tone }: { value: number; tone?: string }) {
  return (
    <div className="meter">
      <i style={{ width: `${Math.max(0, Math.min(100, value))}%`, background: tone }} />
    </div>
  )
}

export function Stat({ label, value, sub, tone }: {
  label: string; value: ReactNode; sub?: ReactNode; tone?: string
}) {
  return (
    <div className="stat">
      <dt>{label}</dt>
      <dd style={{ color: tone }}>{value}</dd>
      {sub && <div className="sub">{sub}</div>}
    </div>
  )
}

export function Callout({ tone = 'default', icon = 'info', children }: {
  tone?: 'default' | 'critical' | 'major' | 'accent'; icon?: IconName; children: ReactNode
}) {
  return (
    <div className={`callout${tone === 'default' ? '' : ` is-${tone}`}`}>
      <Icon name={icon} size={14} />
      <div className="grow">{children}</div>
    </div>
  )
}

export function Empty({ icon = 'file', title, children }: {
  icon?: IconName; title: string; children?: ReactNode
}) {
  return (
    <div className="empty">
      <Icon name={icon} size={26} strokeWidth={1.3} />
      <b>{title}</b>
      {children && <div className="t-sm" style={{ maxWidth: 380 }}>{children}</div>}
    </div>
  )
}

export function Segmented<T extends string>({ options, value, onChange }: {
  options: { value: T; label: string }[]; value: T; onChange: (v: T) => void
}) {
  return (
    <div className="segmented" role="tablist">
      {options.map((option) => (
        <button
          key={option.value} role="tab" aria-selected={value === option.value}
          className={value === option.value ? 'is-on' : ''}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
