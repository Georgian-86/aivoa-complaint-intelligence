/**
 * Intake slice — the draft complaint currently on the analyst's desk.
 *
 * This is the heart of the Redux design. The form is a controlled document, so
 * the store tracks not just values but *provenance*: which fields the agent
 * filled, at what confidence, with what evidence, and which the analyst has
 * since touched. `touched` is what makes a re-run safe — the agent may never
 * overwrite a human edit.
 */
import { createAsyncThunk, createSlice, type PayloadAction } from '@reduxjs/toolkit'
import { api, streamIntake } from '@/api/client'
import type {
  CapaAction, CompletenessGap, ComplaintForm, DuplicateCandidate, ExtractedField,
  IntakeResult, RiskAssessment, RootCauseHypothesis, TraceEntry,
} from '@/api/types'

export type RunPhase = 'idle' | 'running' | 'complete' | 'error'

export interface NodeProgress {
  node: string
  label: string
  status: 'pending' | 'running' | 'ok' | 'error'
  engine?: string | null
  model?: string | null
  duration_ms?: number
  output?: Record<string, unknown> | null
  note?: string | null
}

interface IntakeState {
  form: ComplaintForm
  fields: Record<string, ExtractedField>
  touched: Record<string, true>
  landed: string[]                // fields that just arrived — drives the flash

  phase: RunPhase
  progress: number
  steps: NodeProgress[]
  runId: string | null
  engine: string | null
  models: Record<string, string | null>
  durationMs: number

  sourceText: string | null
  sourceName: string | null
  pasteDraft: string

  summary: string | null
  completeness: number
  gaps: CompletenessGap[]
  duplicates: DuplicateCandidate[]
  risk: RiskAssessment | null
  rootCauses: RootCauseHypothesis[]
  capa: CapaAction[]
  questions: string[]
  trace: TraceEntry[]
  warnings: string[]

  error: string | null
  saving: boolean
  savedId: string | null
  savedReference: string | null
  dismissedDuplicates: string[]
}

const EMPTY_FORM: ComplaintForm = {
  complaint_source: '', customer_name: '', customer_contact: '', customer_country: '',
  product_name: '', product_strength: '', dosage_form: '', batch_number: '',
  manufacturing_date: '', expiry_date: '', quantity_affected: '', quantity_unit: 'units',
  market_country: '', complaint_type: '', complaint_date: '', date_received: '',
  description: '', sample_available: null, severity: '', priority: '',
  status: 'Pending Triage', due_date: '',
}

const initialState: IntakeState = {
  form: { ...EMPTY_FORM },
  fields: {}, touched: {}, landed: [],
  phase: 'idle', progress: 0, steps: [], runId: null, engine: null, models: {}, durationMs: 0,
  sourceText: null, sourceName: null, pasteDraft: '',
  summary: null, completeness: 0, gaps: [], duplicates: [], risk: null,
  rootCauses: [], capa: [], questions: [], trace: [], warnings: [],
  error: null, saving: false, savedId: null, savedReference: null, dismissedDuplicates: [],
}

/** Apply a finished pipeline result, respecting analyst edits. */
function applyResult(state: IntakeState, result: IntakeResult) {
  const landed: string[] = []
  for (const [key, field] of Object.entries(result.fields ?? {})) {
    if (state.touched[key]) continue           // never clobber a human edit
    if (field.value === null || field.value === '') continue
    state.form[key] = field.value as never
    state.fields[key] = field
    landed.push(key)
  }
  for (const key of ['severity', 'priority', 'due_date', 'status'] as const) {
    const incoming = (result.form as Record<string, unknown>)[key]
    if (!state.touched[key] && incoming) {
      state.form[key] = incoming as never
      if (key === 'severity' || key === 'priority') landed.push(key)
    }
  }

  state.landed = landed
  state.runId = result.run_id
  state.engine = result.engine
  state.models = result.models ?? {}
  state.durationMs = result.duration_ms
  state.summary = result.summary
  state.completeness = result.completeness_score
  state.gaps = result.gaps ?? []
  state.duplicates = result.duplicates ?? []
  state.risk = result.risk ?? null
  state.rootCauses = result.root_causes ?? []
  state.capa = result.capa ?? []
  state.questions = result.clarifying_questions ?? []
  state.trace = result.trace ?? []
  state.warnings = result.warnings ?? []
  state.sourceText = result.source_text ?? state.sourceText
  state.phase = 'complete'
  state.progress = 1
  // The draft has been consumed — leaving it in the box invites a
  // duplicate run and makes the attached-source state ambiguous.
  state.pasteDraft = ''
  state.steps = state.steps.map((s) => (s.status === 'pending' || s.status === 'running'
    ? { ...s, status: 'ok' } : s))
}

/** Streaming run — drives the live extraction rail. */
export const runIntakeStream = createAsyncThunk<
  void, { file?: File; text?: string; channel?: string }, { state: { intake: IntakeState } }
>('intake/stream', async (input, { dispatch }) => {
  dispatch(intakeSlice.actions.runStarted({
    sourceName: input.file?.name ?? 'Pasted complaint text',
    sourceText: input.text ?? null,
  }))
  await new Promise<void>((resolve) => {
    const { done } = streamIntake(input, (event) => {
      switch (event.type) {
        case 'start': dispatch(intakeSlice.actions.stepsAnnounced(event.steps)); break
        case 'node': dispatch(intakeSlice.actions.nodeCompleted(event)); break
        case 'complete': dispatch(intakeSlice.actions.runCompleted(event.result)); break
        case 'error': dispatch(intakeSlice.actions.runFailed(event.message)); break
      }
    })
    done.finally(resolve)
  })
})

export const reassess = createAsyncThunk<IntakeResult, void, { state: { intake: IntakeState } }>(
  'intake/reassess',
  async (_void, { getState }) => {
    const { form, sourceText } = getState().intake
    return api.reassess(form, sourceText)
  },
)

export const saveComplaint = createAsyncThunk<
  { id: string; reference: string }, void, { state: { intake: IntakeState } }
>('intake/save', async (_void, { getState }) => {
  const s = getState().intake
  const clean: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(s.form)) {
    if (value === '' || value === undefined) continue
    clean[key] = value
  }
  if (clean.quantity_affected !== undefined) clean.quantity_affected = Number(clean.quantity_affected)

  const saved = await api.createComplaint({
    ...clean,
    intake_channel: s.sourceName ? (s.sourceName === 'Pasted complaint text' ? 'text' : 'document') : 'manual',
    source_document_name: s.sourceName,
    source_text: s.sourceText,
    ai_summary: s.summary,
    ai_risk_score: s.risk?.score ?? null,
    ai_risk_band: s.risk?.band ?? null,
    ai_confidence: overallConfidence(s.fields),
    ai_payload: {
      risk: s.risk, gaps: s.gaps, root_causes: s.rootCauses, capa: s.capa,
      duplicates: s.duplicates, completeness_score: s.completeness,
      field_confidence: Object.fromEntries(
        Object.entries(s.fields).map(([k, v]) => [k, v.confidence]),
      ),
    },
    agent_run_id: s.runId,
  })
  return { id: saved.id, reference: saved.reference }
})

function overallConfidence(fields: Record<string, ExtractedField>): number | null {
  const values = Object.values(fields).filter((f) => f.value !== null && f.value !== '')
  if (!values.length) return null
  return Number((values.reduce((a, f) => a + f.confidence, 0) / values.length).toFixed(3))
}

const intakeSlice = createSlice({
  name: 'intake',
  initialState,
  reducers: {
    fieldChanged(state, action: PayloadAction<{ field: string; value: unknown }>) {
      const { field, value } = action.payload
      state.form[field] = value as never
      state.touched[field] = true
      state.landed = state.landed.filter((f) => f !== field)
      if (state.fields[field]) {
        state.fields[field] = { ...state.fields[field], source: 'analyst', confidence: 1, evidence: null }
      }
    },
    pasteDraftChanged(state, action: PayloadAction<string>) { state.pasteDraft = action.payload },
    landingCleared(state) { state.landed = [] },
    dismissDuplicate(state, action: PayloadAction<string>) {
      state.dismissedDuplicates.push(action.payload)
    },
    runStarted(state, action: PayloadAction<{ sourceName: string; sourceText: string | null }>) {
      state.phase = 'running'
      state.progress = 0.04
      state.error = null
      state.warnings = []
      state.savedId = null
      state.savedReference = null
      state.sourceName = action.payload.sourceName
      state.sourceText = action.payload.sourceText
      state.dismissedDuplicates = []
    },
    stepsAnnounced(state, action: PayloadAction<{ node: string; label: string }[]>) {
      state.steps = action.payload.map((s, i) => ({ ...s, status: i === 0 ? 'running' : 'pending' }))
    },
    nodeCompleted(state, action: PayloadAction<{
      node: string; label: string; status: string; engine: string | null; model: string | null
      duration_ms: number; output: Record<string, unknown> | null; note: string | null; progress: number
    }>) {
      const e = action.payload
      const index = state.steps.findIndex((s) => s.node === e.node)
      if (index !== -1) {
        state.steps[index] = {
          ...state.steps[index],
          status: e.status === 'error' ? 'error' : 'ok',
          engine: e.engine, model: e.model, duration_ms: e.duration_ms,
          output: e.output, note: e.note,
        }
        const next = state.steps.findIndex((s) => s.status === 'pending')
        if (next !== -1) state.steps[next].status = 'running'
      }
      state.progress = e.progress
    },
    runCompleted(state, action: PayloadAction<IntakeResult>) { applyResult(state, action.payload) },
    runFailed(state, action: PayloadAction<string>) {
      state.phase = 'error'
      state.error = action.payload
      state.steps = state.steps.map((s) => (s.status === 'running' ? { ...s, status: 'error' } : s))
    },
    resetIntake() { return { ...initialState, form: { ...EMPTY_FORM } } },
    applyCopilotAction(state, action: PayloadAction<{ field: string; value: unknown }>) {
      state.form[action.payload.field] = action.payload.value as never
      state.touched[action.payload.field] = true
      state.landed = [action.payload.field]
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(reassess.pending, (state) => { state.phase = 'running'; state.progress = 0.3 })
      .addCase(reassess.fulfilled, (state, action) => {
        // A re-assessment refreshes the judgement, never the analyst's data.
        const r = action.payload
        state.risk = r.risk
        state.completeness = r.completeness_score
        state.gaps = r.gaps
        state.duplicates = r.duplicates
        state.rootCauses = r.root_causes
        state.capa = r.capa
        state.summary = r.summary
        state.questions = r.clarifying_questions
        state.trace = r.trace
        state.runId = r.run_id
        state.engine = r.engine
        state.durationMs = r.duration_ms
        state.warnings = r.warnings
        state.phase = 'complete'
        state.progress = 1
        if (!state.touched.severity && r.risk?.severity) state.form.severity = r.risk.severity
        if (!state.touched.priority && r.risk?.priority) state.form.priority = r.risk.priority
      })
      .addCase(reassess.rejected, (state, action) => {
        state.phase = 'error'; state.error = action.error.message ?? 'Re-assessment failed'
      })
      .addCase(saveComplaint.pending, (state) => { state.saving = true; state.error = null })
      .addCase(saveComplaint.fulfilled, (state, action) => {
        state.saving = false
        state.savedId = action.payload.id
        state.savedReference = action.payload.reference
      })
      .addCase(saveComplaint.rejected, (state, action) => {
        state.saving = false; state.error = action.error.message ?? 'Could not save the complaint'
      })
  },
})

export const {
  fieldChanged, pasteDraftChanged, resetIntake, landingCleared,
  applyCopilotAction, dismissDuplicate,
} = intakeSlice.actions
export default intakeSlice.reducer
