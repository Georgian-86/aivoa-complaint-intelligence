export type Severity = 'Critical' | 'Major' | 'Minor'
export type FieldSource = 'llm' | 'heuristic' | 'regex' | 'llm+regex' | 'analyst' | 'default' | 'none'

export interface ExtractedField {
  value: unknown
  confidence: number
  evidence: string | null
  source: FieldSource
}

export interface CompletenessGap {
  field: string
  label: string
  severity: 'blocker' | 'required' | 'recommended'
  reason: string
  suggested_question: string | null
}

export interface DuplicateCandidate {
  complaint_id: string
  reference: string
  score: number
  matched_on: string[]
  product_name: string | null
  batch_number: string | null
  complaint_type: string | null
  severity: string | null
  created_at: string | null
  rationale: string | null
}

export interface RiskDriver { factor: string; weight: number; evidence?: string }

export interface RiskAssessment {
  score: number
  band: 'Low' | 'Moderate' | 'High' | 'Severe' | 'Unassessed'
  severity: Severity | null
  priority: string | null
  patient_safety_impact: string | null
  batch_impact: string | null
  regulatory_flags: string[]
  flag_definitions?: Record<string, string>
  drivers: RiskDriver[]
  rationale: string | null
  recommended_tat_days: number | null
  override?: string
}

export interface RootCauseHypothesis {
  category: string
  hypothesis: string
  likelihood: number
  investigation_step: string | null
}

export interface CapaAction {
  type: 'correction' | 'corrective' | 'preventive'
  action: string
  owner_function: string | null
  due_in_days: number | null
  effectiveness_check: string | null
}

export interface TraceEntry {
  node: string
  label: string
  status: 'ok' | 'error'
  engine: string | null
  model: string | null
  duration_ms: number
  output: Record<string, unknown> | null
  note: string | null
}

export interface IntakeResult {
  run_id: string
  engine: string
  models: Record<string, string | null>
  duration_ms: number
  fields: Record<string, ExtractedField>
  form: ComplaintForm
  summary: string | null
  completeness_score: number
  gaps: CompletenessGap[]
  duplicates: DuplicateCandidate[]
  risk: RiskAssessment
  root_causes: RootCauseHypothesis[]
  capa: CapaAction[]
  clarifying_questions: string[]
  trace: TraceEntry[]
  warnings: string[]
  source_text: string | null
}

export interface ComplaintForm {
  complaint_source?: string | null
  customer_name?: string | null
  customer_contact?: string | null
  customer_country?: string | null
  product_name?: string | null
  product_strength?: string | null
  dosage_form?: string | null
  batch_number?: string | null
  manufacturing_date?: string | null
  expiry_date?: string | null
  quantity_affected?: number | string | null
  quantity_unit?: string | null
  market_country?: string | null
  complaint_type?: string | null
  complaint_date?: string | null
  date_received?: string | null
  description?: string | null
  sample_available?: boolean | null
  severity?: string | null
  priority?: string | null
  status?: string | null
  due_date?: string | null
  [key: string]: unknown
}

export interface Complaint extends ComplaintForm {
  id: string
  reference: string
  intake_channel: string
  source_document_name: string | null
  ai_summary: string | null
  ai_risk_score: number | null
  ai_risk_band: string | null
  ai_confidence: number | null
  ai_payload: Record<string, unknown> | null
  created_at: string
  updated_at: string
  created_by: string
}

export interface AuditEvent {
  id: string
  actor: string
  actor_type: 'human' | 'agent'
  action: string
  detail: string | null
  changes: Record<string, unknown> | null
  created_at: string
}

export interface AgentRunSummary {
  id: string
  channel: string
  source_name: string | null
  status: string
  engine: string
  model_extraction: string | null
  model_reasoning: string | null
  duration_ms: number | null
  created_at: string
  traces: TraceEntry[]
}

export interface ComplaintDetail extends Complaint {
  source_text: string | null
  audit_events: AuditEvent[]
  agent_runs: AgentRunSummary[]
}

export interface Taxonomy {
  complaint_sources: string[]
  complaint_types: string[]
  severities: Severity[]
  severity_definitions: Record<string, string>
  severity_tat_days: Record<string, number>
  priorities: string[]
  dosage_forms: string[]
  statuses: string[]
  root_cause_categories: string[]
}

export interface Analytics {
  total: number
  open_count: number
  overdue_count: number
  by_severity: Record<string, number>
  by_status: Record<string, number>
  by_type: { name: string; count: number }[]
  by_month: { month: string; count: number }[]
  avg_risk_score: number | null
  ai_assisted_share: number
  top_products: { name: string; count: number }[]
  recurrence: {
    product_name: string
    complaint_type: string
    count: number
    batch_count: number
    batches: string[]
    worst_severity: string
    latest: string
  }[]
}

export interface PipelineInfo {
  steps: { node: string; label: string }[]
  engine: string
  models: { extraction: string; reasoning: string }
  llm_configured: boolean
  supported_formats: string[]
  max_upload_mb: number
}

export interface CopilotAction { field: string; value: unknown; reason: string | null }
export interface CopilotResponse {
  reply: string
  engine: string
  model: string | null
  suggestions: string[]
  actions: CopilotAction[]
}

export type StreamEvent =
  | { type: 'start'; run_id: string; steps: { node: string; label: string }[]; engine: string }
  | { type: 'node'; node: string; label: string; status: string; engine: string | null; model: string | null; duration_ms: number; output: Record<string, unknown> | null; note: string | null; progress: number }
  | { type: 'complete'; result: IntakeResult }
  | { type: 'error'; message: string }
