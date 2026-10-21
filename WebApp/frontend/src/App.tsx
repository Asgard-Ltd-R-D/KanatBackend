import { HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Layout } from './layout/Layout'
import { SessionList } from './pages/SessionList'
import { SessionDetail } from './pages/SessionDetail'
import { Settings } from './pages/Settings'
import { useDarkMode } from './hooks/useDarkMode'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      staleTime: 5_000,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
    },
  },
})

function DarkModeInit() {
  useDarkMode()
  return null
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <DarkModeInit />
      <HashRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<SessionList />} />
            <Route path="sessions/:id" element={<SessionDetail />} />
            <Route path="settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </HashRouter>
    </QueryClientProvider>
  )
}
