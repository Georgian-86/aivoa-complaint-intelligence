/** Complaint register: list, filters, selected record, analytics. */
import { createAsyncThunk, createSlice, type PayloadAction } from '@reduxjs/toolkit'
import { api } from '@/api/client'
import type { Analytics, Complaint, ComplaintDetail } from '@/api/types'

interface Filters {
  q: string
  severity: string[]
  status: string[]
  complaint_type: string[]
  page: number
  page_size: number
  sort: string
}

interface ComplaintsState {
  items: Complaint[]
  total: number
  filters: Filters
  listStatus: 'idle' | 'loading' | 'ready' | 'error'
  detail: ComplaintDetail | null
  detailStatus: 'idle' | 'loading' | 'ready' | 'error'
  analytics: Analytics | null
  analyticsStatus: 'idle' | 'loading' | 'ready' | 'error'
  error: string | null
}

const initialState: ComplaintsState = {
  items: [], total: 0,
  filters: { q: '', severity: [], status: [], complaint_type: [], page: 1, page_size: 25, sort: '-created_at' },
  listStatus: 'idle', detail: null, detailStatus: 'idle',
  analytics: null, analyticsStatus: 'idle', error: null,
}

export const fetchComplaints = createAsyncThunk<
  { items: Complaint[]; total: number }, void, { state: { complaints: ComplaintsState } }
>('complaints/fetch', async (_v, { getState }) => {
  const f = getState().complaints.filters
  return api.listComplaints({ ...f })
})

export const fetchComplaint = createAsyncThunk('complaints/fetchOne', (id: string) =>
  api.getComplaint(id))

export const fetchAnalytics = createAsyncThunk('complaints/analytics', () => api.analytics())

export const changeStatus = createAsyncThunk(
  'complaints/status',
  ({ id, status, note }: { id: string; status: string; note?: string }) =>
    api.setStatus(id, status, note),
)

const complaintsSlice = createSlice({
  name: 'complaints',
  initialState,
  reducers: {
    filterChanged(state, action: PayloadAction<Partial<Filters>>) {
      state.filters = { ...state.filters, ...action.payload, page: action.payload.page ?? 1 }
    },
    toggleFacet(state, action: PayloadAction<{ key: 'severity' | 'status' | 'complaint_type'; value: string }>) {
      const { key, value } = action.payload
      const current = state.filters[key]
      state.filters[key] = current.includes(value)
        ? current.filter((v) => v !== value)
        : [...current, value]
      state.filters.page = 1
    },
    filtersCleared(state) { state.filters = { ...initialState.filters } },
    detailCleared(state) { state.detail = null; state.detailStatus = 'idle' },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchComplaints.pending, (state) => { state.listStatus = 'loading' })
      .addCase(fetchComplaints.fulfilled, (state, action) => {
        state.items = action.payload.items
        state.total = action.payload.total
        state.listStatus = 'ready'
      })
      .addCase(fetchComplaints.rejected, (state, action) => {
        state.listStatus = 'error'; state.error = action.error.message ?? 'Could not load the register'
      })
      .addCase(fetchComplaint.pending, (state) => { state.detailStatus = 'loading' })
      .addCase(fetchComplaint.fulfilled, (state, action) => {
        state.detail = action.payload; state.detailStatus = 'ready'
      })
      .addCase(fetchComplaint.rejected, (state) => { state.detailStatus = 'error' })
      .addCase(fetchAnalytics.pending, (state) => { state.analyticsStatus = 'loading' })
      .addCase(fetchAnalytics.fulfilled, (state, action) => {
        state.analytics = action.payload; state.analyticsStatus = 'ready'
      })
      .addCase(fetchAnalytics.rejected, (state) => { state.analyticsStatus = 'error' })
      .addCase(changeStatus.fulfilled, (state, action) => {
        state.detail = action.payload
        state.items = state.items.map((c) => (c.id === action.payload.id ? { ...c, ...action.payload } : c))
      })
  },
})

export const { filterChanged, toggleFacet, filtersCleared, detailCleared } = complaintsSlice.actions
export default complaintsSlice.reducer
