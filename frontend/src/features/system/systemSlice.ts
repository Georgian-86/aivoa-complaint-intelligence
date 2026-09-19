/** Reference data + environment status, fetched once on boot. */
import { createAsyncThunk, createSlice, type PayloadAction } from '@reduxjs/toolkit'
import { api } from '@/api/client'
import type { PipelineInfo, Taxonomy } from '@/api/types'

type Theme = 'light' | 'dark'

interface SystemState {
  taxonomy: Taxonomy | null
  pipeline: PipelineInfo | null
  health: Record<string, unknown> | null
  status: 'idle' | 'loading' | 'ready' | 'offline'
  theme: Theme
  railCollapsed: boolean
  toast: { id: number; tone: 'ok' | 'warn' | 'error'; message: string } | null
}

const storedTheme = (): Theme => {
  if (typeof document === 'undefined') return 'light'
  return (document.documentElement.dataset.theme as Theme) ?? 'light'
}

const initialState: SystemState = {
  taxonomy: null, pipeline: null, health: null, status: 'idle',
  theme: storedTheme(),
  railCollapsed: localStorage.getItem('aivoa.rail') === 'collapsed',
  toast: null,
}

export const bootstrap = createAsyncThunk('system/bootstrap', async () => {
  const [taxonomy, pipeline, health] = await Promise.all([
    api.taxonomy(), api.pipeline(), api.health(),
  ])
  return { taxonomy, pipeline, health }
})

const systemSlice = createSlice({
  name: 'system',
  initialState,
  reducers: {
    themeToggled(state) {
      state.theme = state.theme === 'dark' ? 'light' : 'dark'
      document.documentElement.dataset.theme = state.theme
      localStorage.setItem('aivoa.theme', state.theme)
    },
    railToggled(state) {
      state.railCollapsed = !state.railCollapsed
      localStorage.setItem('aivoa.rail', state.railCollapsed ? 'collapsed' : 'expanded')
    },
    notify(state, action: PayloadAction<{ tone: 'ok' | 'warn' | 'error'; message: string }>) {
      state.toast = { id: Date.now(), ...action.payload }
    },
    toastDismissed(state) { state.toast = null },
  },
  extraReducers: (builder) => {
    builder
      .addCase(bootstrap.pending, (state) => { state.status = 'loading' })
      .addCase(bootstrap.fulfilled, (state, action) => {
        state.taxonomy = action.payload.taxonomy
        state.pipeline = action.payload.pipeline
        state.health = action.payload.health
        state.status = 'ready'
      })
      .addCase(bootstrap.rejected, (state) => { state.status = 'offline' })
  },
})

export const { themeToggled, railToggled, notify, toastDismissed } = systemSlice.actions
export default systemSlice.reducer
