/** The conversational assistant beside the form. */
import { createAsyncThunk, createSlice, type PayloadAction } from '@reduxjs/toolkit'
import { api } from '@/api/client'
import type { ComplaintForm, CopilotAction } from '@/api/types'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  actions?: CopilotAction[]
  engine?: string
  model?: string | null
  at: number
}

interface CopilotState {
  threadId: string
  messages: ChatMessage[]
  draft: string
  pending: boolean
  suggestions: string[]
  error: string | null
}

const uid = () => Math.random().toString(36).slice(2, 10)

const GREETING: ChatMessage = {
  id: 'greeting',
  role: 'assistant',
  at: Date.now(),
  content:
    'Upload a complaint document or paste the e-mail text and I will read it, populate the '
    + 'record and classify the GMP risk. You can also ask me about the record at any point — '
    + 'why a severity was assigned, what is still missing, or what to do next.',
}

const initialState: CopilotState = {
  threadId: uid(),
  messages: [GREETING],
  draft: '',
  pending: false,
  suggestions: [
    'Why was this severity assigned?',
    'What is still missing from this record?',
    'Draft the acknowledgement to the complainant.',
  ],
  error: null,
}

export const askCopilot = createAsyncThunk<
  { reply: string; actions: CopilotAction[]; suggestions: string[]; engine: string; model: string | null },
  { message: string; form: ComplaintForm; sourceText?: string | null },
  { state: { copilot: CopilotState } }
>('copilot/ask', async ({ message, form, sourceText }, { getState }) => {
  const response = await api.copilot({
    thread_id: getState().copilot.threadId,
    message, form, source_text: sourceText ?? null,
  })
  return response
})

const copilotSlice = createSlice({
  name: 'copilot',
  initialState,
  reducers: {
    draftChanged(state, action: PayloadAction<string>) { state.draft = action.payload },
    systemNote(state, action: PayloadAction<string>) {
      state.messages.push({ id: uid(), role: 'system', content: action.payload, at: Date.now() })
    },
    threadReset() { return { ...initialState, threadId: uid(), messages: [GREETING] } },
  },
  extraReducers: (builder) => {
    builder
      .addCase(askCopilot.pending, (state, action) => {
        state.messages.push({
          id: uid(), role: 'user', content: action.meta.arg.message, at: Date.now(),
        })
        state.draft = ''
        state.pending = true
        state.error = null
      })
      .addCase(askCopilot.fulfilled, (state, action) => {
        state.pending = false
        state.messages.push({
          id: uid(), role: 'assistant', content: action.payload.reply,
          actions: action.payload.actions, engine: action.payload.engine,
          model: action.payload.model, at: Date.now(),
        })
        if (action.payload.suggestions?.length) state.suggestions = action.payload.suggestions
      })
      .addCase(askCopilot.rejected, (state, action) => {
        state.pending = false
        state.error = action.error.message ?? 'The assistant did not respond.'
        state.messages.push({
          id: uid(), role: 'assistant', at: Date.now(),
          content: `I could not answer that — ${state.error}`,
        })
      })
  },
})

export const { draftChanged, systemNote, threadReset } = copilotSlice.actions
export default copilotSlice.reducer
