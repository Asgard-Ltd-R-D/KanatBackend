import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Bundled with the app: the range PC is offline
import '@fontsource-variable/inter'
import './index.css'
import { App } from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
