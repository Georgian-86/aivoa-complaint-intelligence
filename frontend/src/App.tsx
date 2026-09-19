import { useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/AppShell'
import { IntakePage } from '@/pages/IntakePage'
import { RegisterPage } from '@/pages/RegisterPage'
import { ComplaintDetailPage } from '@/pages/ComplaintDetailPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { useAppDispatch } from '@/app/store'
import { bootstrap } from '@/features/system/systemSlice'

export default function App() {
  const dispatch = useAppDispatch()
  useEffect(() => { dispatch(bootstrap()) }, [dispatch])

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/intake" replace />} />
        <Route path="/intake" element={<IntakePage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/register/:id" element={<ComplaintDetailPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="*" element={<Navigate to="/intake" replace />} />
      </Routes>
    </AppShell>
  )
}
