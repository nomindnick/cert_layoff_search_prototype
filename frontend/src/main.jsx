import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.jsx'
import { bootstrapToken } from './lib/api'

// Must run before React mounts: page effects fire child-first, so a page's
// mount-time API call would otherwise race ahead of Layout's bootstrap, 401,
// and bounce a valid magic link to /no-access.
bootstrapToken()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
