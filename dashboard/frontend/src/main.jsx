import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import VectorSpacePage from './pages/VectorSpacePage.jsx'
import RadarPage from './pages/RadarPage.jsx'
import './theme/cyberpunk.css'

const root = document.getElementById('root')
const isVectorSpaceRoute = window.location.pathname === '/vectordb'
const isRadarRoute = window.location.pathname === '/radar'

ReactDOM.createRoot(root).render(
  isVectorSpaceRoute ? <VectorSpacePage /> : isRadarRoute ? <RadarPage /> : <App />,
)
