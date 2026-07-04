import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import VectorSpacePage from './pages/VectorSpacePage.jsx'
import './theme/cyberpunk.css'

const root = document.getElementById('root')
const isVectorSpaceRoute = window.location.pathname === '/vectordb'

ReactDOM.createRoot(root).render(
  isVectorSpaceRoute ? <VectorSpacePage /> : <App />,
)
