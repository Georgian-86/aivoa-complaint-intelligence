import { configureStore } from '@reduxjs/toolkit'
import { useDispatch, useSelector, type TypedUseSelectorHook } from 'react-redux'
import intake from '@/features/intake/intakeSlice'
import complaints from '@/features/complaints/complaintsSlice'
import copilot from '@/features/copilot/copilotSlice'
import system from '@/features/system/systemSlice'

export const store = configureStore({
  reducer: { intake, complaints, copilot, system },
  middleware: (getDefault) =>
    // File objects are passed to a thunk argument, not stored in state.
    getDefault({ serializableCheck: { ignoredActionPaths: ['meta.arg.file'] } }),
})

export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch

export const useAppDispatch: () => AppDispatch = useDispatch
export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector
