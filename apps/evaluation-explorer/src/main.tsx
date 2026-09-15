import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import '@linger/architecture-map/src/map.css'
import './styles.css'

const root = document.getElementById('root')
if (!root) throw new Error('The explorer root element is missing.')
createRoot(root).render(<StrictMode><App /></StrictMode>)
