import { useCallback, useEffect, useRef, useState } from 'react'
import { useAppDispatch, useAppSelector } from '@/app/store'
import {
  applyCopilotAction, pasteDraftChanged, runIntakeStream,
} from '@/features/intake/intakeSlice'
import { askCopilot, draftChanged, systemNote } from '@/features/copilot/copilotSlice'
import { notify } from '@/features/system/systemSlice'
import { Icon } from '../Icon'
import './intake.css'

const MODEL_SHORT: Record<string, string> = {
  // Assignment-mandated models. Kept here in case a deployment's Groq
  // account still has access to them (see docs/DEPLOYMENT.md, Step 0).
  'gemma2-9b-it': 'gemma2-9b',
  'llama-3.3-70b-versatile': 'llama-3.3-70b',
  // Current defaults -- gemma2-9b-it was decommissioned by Groq and
  // llama-3.3-70b-versatile is Enterprise-tier-gated as of this build.
  'openai/gpt-oss-20b': 'gpt-oss-20b',
  'openai/gpt-oss-120b': 'gpt-oss-120b',
}

/* ── Live agent rail ───────────────────────────────────────────────────────── */
function AgentRail() {
  const { steps, phase, progress, durationMs, engine } = useAppSelector((s) => s.intake)
  if (!steps.length) return null

  const digest = (output: Record<string, unknown> | null | undefined) => {
    if (!output) return null
    const parts: string[] = []
    if ('fields_populated' in output) parts.push(`${output.fields_populated}/${output.fields_total} fields`)
    if ('mean_confidence' in output) parts.push(`μ ${Number(output.mean_confidence).toFixed(2)}`)
    if ('score' in output && 'missing' in output) parts.push(`${output.score}% complete · ${output.missing} gaps`)
    if ('matches' in output) parts.push(`${output.matches} candidate${output.matches === 1 ? '' : 's'}`)
    if ('severity' in output && 'band' in output) parts.push(`${output.severity} · ${output.score}/100`)
    if ('hypotheses' in output) parts.push(`${output.hypotheses} hypotheses · ${output.capa_actions} CAPA`)
    if ('word_count' in output) parts.push(`${output.word_count} words`)
    if ('overall_confidence' in output) parts.push(`overall ${Number(output.overall_confidence).toFixed(2)}`)
    return parts.join('  ·  ') || null
  }

  return (
    <div className="card">
      <div className="card-head" style={{ padding: '10px var(--sp-4)' }}>
        <Icon name="trace" size={14} style={{ color: 'var(--accent)' }} />
        <span className="t-label grow">Extraction pipeline</span>
        {phase === 'complete' && (
          <span className="t-mono t-xs t-muted">{(durationMs / 1000).toFixed(2)}s</span>
        )}
      </div>

      {phase === 'running' && (
        <div className="meter" style={{ borderRadius: 0, height: 2 }}>
          <i style={{ width: `${progress * 100}%` }} />
        </div>
      )}

      <div className="card-body" style={{ padding: 'var(--sp-4)' }}>
        <div className="agent-rail">
          {steps.map((step) => (
            <div key={step.node} className={`agent-step is-${step.status}`}>
              <span className="agent-node">
                {step.status === 'ok' && <Icon name="check" size={9} strokeWidth={2.6} />}
                {step.status === 'error' && <Icon name="close" size={9} strokeWidth={2.6} />}
              </span>
              <div>
                <div className="agent-label">{step.label}</div>
                {(step.output || step.note) && (
                  <div className="agent-detail">
                    {step.engine && (
                      <span className={`agent-engine${step.engine !== 'groq' ? ' is-rules' : ''}`}>
                        {step.model ? MODEL_SHORT[step.model] ?? step.model : step.engine}
                      </span>
                    )}
                    {digest(step.output)}
                    {step.note && <div style={{ color: 'var(--major)', marginTop: 2 }}>{step.note}</div>}
                  </div>
                )}
              </div>
              <span className="agent-ms">
                {step.duration_ms !== undefined && step.status !== 'pending'
                  ? `${step.duration_ms} ms` : ''}
              </span>
            </div>
          ))}
        </div>
        {engine === 'heuristic' && phase === 'complete' && (
          <div className="callout is-major" style={{ marginTop: 'var(--sp-3)' }}>
            <Icon name="alert" size={13} />
            <span>
              Run completed on the deterministic engine — no <code className="t-mono">GROQ_API_KEY</code>{' '}
              is configured. Every value must be verified before saving.
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

/* ── Intake surface: drop, paste, run ──────────────────────────────────────── */
function IntakeSurface() {
  const dispatch = useAppDispatch()
  const pipeline = useAppSelector((s) => s.system.pipeline)
  const { phase, pasteDraft, sourceName } = useAppSelector((s) => s.intake)
  const [over, setOver] = useState(false)
  const [composing, setComposing] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const running = phase === 'running'
  // Once a source has been consumed the intake surface collapses to a single
  // pill. Leaving the dropzone and the textarea on screen invites a second run
  // against a source the analyst has already processed.
  const attached = Boolean(sourceName) && phase !== 'idle'

  const accepted = pipeline?.supported_formats ?? ['.pdf', '.docx', '.txt', '.eml']

  const start = useCallback((payload: { file?: File; text?: string }) => {
    dispatch(runIntakeStream(payload))
    dispatch(systemNote(
      payload.file
        ? `Reading ${payload.file.name} …`
        : 'Reading the pasted complaint text …',
    ))
  }, [dispatch])

  const onFiles = (files: FileList | null) => {
    const file = files?.[0]
    if (!file) return
    const max = (pipeline?.max_upload_mb ?? 10) * 1024 * 1024
    if (file.size > max) {
      dispatch(notify({ tone: 'error', message: `${file.name} exceeds the ${pipeline?.max_upload_mb ?? 10} MB limit.` }))
      return
    }
    start({ file })
  }

  return (
    <div className="card">
      <div className="assist-head">
        <span className="assist-mark"><Icon name="sparkle" size={14} /></span>
        <div className="grow">
          <div className="t-sm" style={{ fontWeight: 600 }}>AI Complaint Intake Assistant</div>
          <div className="t-xs t-muted">
            {pipeline?.llm_configured
              ? `${MODEL_SHORT[pipeline.models.extraction] ?? pipeline.models.extraction} · LangGraph`
              : 'Deterministic engine · LangGraph'}
          </div>
        </div>
        <span className="chip chip-accent">BETA</span>
      </div>

      <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-3)' }}>
        {attached ? (
          <div className="source-pill">
            <Icon name="file" size={15} style={{ color: 'var(--accent)' }} />
            <div className="grow" style={{ minWidth: 0 }}>
              <b className="truncate" style={{ display: 'block' }}>{sourceName}</b>
              <span className="t-xs t-muted">
                {running ? 'Processing…' : phase === 'error' ? 'Failed' : 'Processed'}
              </span>
            </div>
            <button className="btn btn-ghost btn-sm"
              onClick={() => { setComposing(true); inputRef.current?.click() }}>
              Replace
            </button>
          </div>
        ) : (
          <div
            className={`dropzone${over ? ' is-over' : ''}`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setOver(true) }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); onFiles(e.dataTransfer.files) }}
            role="button" tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
          >
            <Icon name="upload" size={22} strokeWidth={1.4} style={{ color: 'var(--accent)' }} />
            <b>Drop the complaint document here</b>
            <span className="t-xs t-muted">or <span className="link">browse your files</span></span>
          </div>
        )}

        <input
          ref={inputRef} type="file" hidden accept={accepted.join(',')}
          onChange={(e) => { onFiles(e.target.files); e.target.value = '' }}
        />

        {attached && !composing ? (
          <button className="btn btn-ghost btn-sm" style={{ alignSelf: 'flex-start' }}
            onClick={() => setComposing(true)}>
            <Icon name="plus" size={12} /> Process different text
          </button>
        ) : (
          <>
        <div className="divider-or">or</div>

        <textarea
          className="textarea" rows={3}
          placeholder="Paste the complaint e-mail or text here…"
          value={pasteDraft}
          onChange={(e) => dispatch(pasteDraftChanged(e.target.value))}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && pasteDraft.trim().length > 20) {
              start({ text: pasteDraft })
            }
          }}
        />
        <button
          className="btn btn-primary" style={{ width: '100%' }}
          disabled={running || pasteDraft.trim().length < 20}
          onClick={() => { setComposing(false); start({ text: pasteDraft }) }}
        >
          <Icon name="sparkle" size={14} />
          {running ? 'Extracting…' : 'Extract & assess'}
        </button>
          </>
        )}

        <div className="formats">
          <Icon name="info" size={12} />
          <span>
            {accepted.join(' · ').toUpperCase().replace(/\./g, '')} · max {pipeline?.max_upload_mb ?? 10} MB
          </span>
        </div>
      </div>
    </div>
  )
}

/* ── Chat ──────────────────────────────────────────────────────────────────── */
function Chat() {
  const dispatch = useAppDispatch()
  const { messages, draft, pending, suggestions } = useAppSelector((s) => s.copilot)
  const { form, sourceText } = useAppSelector((s) => s.intake)
  const logRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, pending])

  const send = (message: string) => {
    const trimmed = message.trim()
    if (!trimmed || pending) return
    dispatch(askCopilot({ message: trimmed, form, sourceText }))
  }

  return (
    <div className="card chat">
      <div className="card-head" style={{ padding: '10px var(--sp-4)' }}>
        <Icon name="sparkle" size={13} style={{ color: 'var(--accent)' }} />
        <span className="t-label grow">Ask about this complaint</span>
      </div>

      <div className="chat-log" ref={logRef}>
        {messages.map((message) => (
          <div key={message.id} className={`msg is-${message.role}`}>
            {message.role !== 'system' && (
              <span className="msg-avatar">
                <Icon name={message.role === 'user' ? 'intake' : 'sparkle'} size={11} />
              </span>
            )}
            <div className="msg-body">
              {message.content}
              {message.actions && message.actions.length > 0 && (
                <div className="msg-actions">
                  {message.actions.map((action, index) => (
                    <button
                      key={index} className="msg-action"
                      onClick={() => {
                        dispatch(applyCopilotAction({ field: action.field, value: action.value }))
                        dispatch(notify({ tone: 'ok', message: `${action.field} set to “${String(action.value)}”.` }))
                      }}
                    >
                      <Icon name="arrow" size={12} style={{ color: 'var(--accent)' }} />
                      <span className="grow">
                        Set <code>{action.field}</code> to <b>{String(action.value)}</b>
                        {action.reason && <div className="t-muted" style={{ marginTop: 2 }}>{action.reason}</div>}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {pending && (
          <div className="msg is-assistant">
            <span className="msg-avatar"><Icon name="sparkle" size={11} /></span>
            <div className="msg-body">
              <span className="typing"><i /><i /><i /></span>
            </div>
          </div>
        )}
      </div>

      {!pending && (
        <div className="chat-suggestions">
          {suggestions.slice(0, 3).map((suggestion) => (
            <button key={suggestion} className="suggestion" onClick={() => send(suggestion)}>
              {suggestion}
            </button>
          ))}
        </div>
      )}

      <div className="chat-compose">
        <textarea
          className="chat-input" rows={1} placeholder="Ask me anything about this complaint…"
          value={draft}
          onChange={(e) => dispatch(draftChanged(e.target.value))}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(draft) }
          }}
        />
        <button className="btn btn-primary btn-icon" onClick={() => send(draft)}
          disabled={pending || !draft.trim()} aria-label="Send">
          <Icon name="send" size={14} />
        </button>
      </div>
      <div className="chat-foot">
        AI responses may contain errors. A qualified reviewer must verify every entry.
      </div>
    </div>
  )
}

export function AssistantPanel() {
  return (
    <div className="assistant">
      <IntakeSurface />
      <AgentRail />
      <Chat />
    </div>
  )
}
