import { useState } from 'react'
import type { ExtractedField } from '@/api/types'
import './ui.css'

const SOURCE_LABEL: Record<string, string> = {
  llm: 'Extracted by model',
  'llm+regex': 'Model + pattern agreement',
  regex: 'Pattern match',
  heuristic: 'Rule engine',
  analyst: 'Entered by analyst',
  default: 'System default',
  none: 'Not populated',
}

/**
 * Field-level provenance. In a regulated workflow the analyst has to be able
 * to challenge any machine-written value, so every AI-populated field exposes
 * its confidence, its origin and the verbatim sentence it came from.
 */
export function ConfidenceBadge({ field }: { field: ExtractedField }) {
  const [open, setOpen] = useState(false)
  if (!field || field.source === 'none' || field.value === null || field.value === '') return null

  const pct = Math.round(field.confidence * 100)
  const filled = field.confidence >= 0.8 ? 3 : field.confidence >= 0.5 ? 2 : 1
  const tone = field.source === 'analyst' ? 'is-analyst' : field.confidence < 0.5 ? 'is-low' : ''

  return (
    <span
      className={`conf ${tone}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      tabIndex={0}
      role="button"
      aria-label={`Confidence ${pct}%, ${SOURCE_LABEL[field.source] ?? field.source}`}
    >
      <span className="conf-bars" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <span key={i} className={`conf-bar${i < filled ? ' is-on' : ''}`} />
        ))}
      </span>
      {field.source === 'analyst' ? 'YOU' : `${pct}%`}

      {open && (
        <span className="conf-pop" role="tooltip">
          <span className="src">
            <span>{SOURCE_LABEL[field.source] ?? field.source}</span>
            <span>{pct}% confidence</span>
          </span>
          {field.evidence ? (
            <blockquote>“{field.evidence}”</blockquote>
          ) : (
            <span>
              No verbatim evidence was captured for this value — verify it against the source
              document before saving.
            </span>
          )}
        </span>
      )}
    </span>
  )
}
