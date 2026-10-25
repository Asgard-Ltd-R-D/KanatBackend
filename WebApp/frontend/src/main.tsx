import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Bundled with the app: the range PC is offline
import '@fontsource-variable/inter'
import './index.css'
import { App } from './App'
import { startLogging } from './utils/logger'

startLogging()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
