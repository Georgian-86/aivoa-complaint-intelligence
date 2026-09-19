/**
 * Typed HTTP client.
 *
 * One place that knows about the wire: every slice talks to this module, so
 * error shape, base URL and the SSE parsing live in exactly one file.
 */
import type {
  Analytics, Complaint, ComplaintDetail, ComplaintForm, CopilotResponse,
  IntakeResult, PipelineInfo, StreamEvent, Taxonomy,
} from './types'

const BASE = import.meta.env.VITE_API_BASE ?? '/api/v1'

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly detail?: unknown) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        ...init?.headers,
      },
    })
  } catch {
    throw new ApiError(
      'Cannot reach the API. Start the backend with `uvicorn app.main:app --reload`.', 0,
    )
  }

  if (response.status === 204) return undefined as T
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = (payload as { detail?: unknown } | null)?.detail
    throw new ApiError(
      typeof detail === 'string' ? detail : `Request failed (${response.status})`,
      response.status, detail,
    )
  }
  return payload as T
}

const qs = (params: Record<string, unknown>) => {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value)) value.forEach((v) => search.append(key, String(v)))
    else search.append(key, String(value))
  }
  const s = search.toString()
  return s ? `?${s}` : ''
}

export const api = {
  health: () => request<Record<string, unknown>>('/health'),
  pipeline: () => request<PipelineInfo>('/intake/pipeline'),
  taxonomy: () => request<Taxonomy>('/complaints/taxonomy'),

  intakeText: (text: string, channel: 'text' | 'email' = 'text') =>
    request<IntakeResult>('/intake/text', {
      method: 'POST', body: JSON.stringify({ text, channel }),
    }),

  reassess: (form: ComplaintForm, sourceText?: string | null) =>
    request<IntakeResult>('/intake/reassess', {
      method: 'POST', body: JSON.stringify({ form, source_text: sourceText ?? null }),
    }),

  listComplaints: (params: Record<string, unknown>) =>
    request<{ items: Complaint[]; total: number; page: number; page_size: number }>(
      `/complaints${qs(params)}`,
    ),

  getComplaint: (id: string) => request<ComplaintDetail>(`/complaints/${id}`),

  createComplaint: (payload: Record<string, unknown>) =>
    request<ComplaintDetail>('/complaints', { method: 'POST', body: JSON.stringify(payload) }),

  updateComplaint: (id: string, payload: Record<string, unknown>) =>
    request<ComplaintDetail>(`/complaints/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),

  setStatus: (id: string, status: string, note?: string) =>
    request<ComplaintDetail>(`/complaints/${id}/status`, {
      method: 'POST', body: JSON.stringify({ status, note }),
    }),

  analytics: () => request<Analytics>('/analytics/overview'),

  copilot: (payload: {
    thread_id: string; message: string; form: ComplaintForm
    source_text?: string | null; complaint_id?: string | null
  }) => request<CopilotResponse>('/copilot', { method: 'POST', body: JSON.stringify(payload) }),
}

/**
 * Run the intake pipeline over SSE.
 *
 * `fetch` + a manual reader rather than `EventSource`, because the request is a
 * POST carrying a file. Returns an abort handle so the UI can cancel a run.
 */
export function streamIntake(
  input: { file?: File; text?: string; channel?: string },
  onEvent: (event: StreamEvent) => void,
): { abort: () => void; done: Promise<void> } {
  const controller = new AbortController()
  const body = new FormData()
  if (input.file) body.append('file', input.file)
  if (input.text) body.append('text', input.text)
  body.append('channel', input.channel ?? (input.file ? 'document' : 'text'))

  const done = (async () => {
    let response: Response
    try {
      response = await fetch(`${BASE}/intake/stream`, {
        method: 'POST', body, signal: controller.signal,
      })
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        onEvent({ type: 'error', message: 'Cannot reach the API. Is the backend running?' })
      }
      return
    }

    if (!response.ok || !response.body) {
      const payload = await response.json().catch(() => null)
      const detail = (payload as { detail?: string } | null)?.detail
      onEvent({ type: 'error', message: detail ?? `Upload failed (${response.status})` })
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      for (;;) {
        const { done: finished, value } = await reader.read()
        if (finished) break
        buffer += decoder.decode(value, { stream: true })

        // SSE frames are separated by a blank line.
        let boundary = buffer.indexOf('\n\n')
        while (boundary !== -1) {
          const frame = buffer.slice(0, boundary)
          buffer = buffer.slice(boundary + 2)
          boundary = buffer.indexOf('\n\n')

          let event = 'message'
          const dataLines: string[] = []
          for (const line of frame.split('\n')) {
            if (line.startsWith('event:')) event = line.slice(6).trim()
            else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
          }
          if (!dataLines.length) continue

          let data: unknown
          try { data = JSON.parse(dataLines.join('\n')) } catch { continue }

          if (event === 'complete') onEvent({ type: 'complete', result: data as IntakeResult })
          else if (event === 'error') onEvent({ type: 'error', message: (data as { message: string }).message })
          else if (event === 'start') onEvent({ type: 'start', ...(data as object) } as StreamEvent)
          else if (event === 'node') onEvent({ type: 'node', ...(data as object) } as StreamEvent)
        }
      }
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        onEvent({ type: 'error', message: (error as Error).message })
      }
    }
  })()

  return { abort: () => controller.abort(), done }
}
