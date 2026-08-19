import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import VectorSpacePage from './pages/VectorSpacePage.jsx'
import RadarPage from './pages/RadarPage.jsx'
import ReplayPage from './pages/ReplayPage.jsx'
import './theme/cyberpunk.css'

const root = document.getElementById('root')
const route = window.location.pathname

ReactDOM.createRoot(root).render(
  route === '/vectordb' ? <VectorSpacePage />
    : route === '/radar' ? <RadarPage />
    : route === '/replay' ? <ReplayPage />
    : <App />
)
