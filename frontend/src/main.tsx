import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/manrope/latin-400.css'
import '@fontsource/manrope/latin-500.css'
import '@fontsource/manrope/latin-600.css'
import '@fontsource/manrope/latin-700.css'
import '@fontsource/manrope/latin-800.css'
import '@fontsource/manrope/latin-ext-400.css'
import '@fontsource/manrope/latin-ext-500.css'
import '@fontsource/manrope/latin-ext-600.css'
import '@fontsource/manrope/latin-ext-700.css'
import '@fontsource/manrope/latin-ext-800.css'
import '@fontsource/montserrat/latin-400.css'
import '@fontsource/montserrat/latin-700.css'
import '@fontsource/montserrat/latin-800.css'
import '@fontsource/montserrat/latin-ext-400.css'
import '@fontsource/montserrat/latin-ext-700.css'
import '@fontsource/montserrat/latin-ext-800.css'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
