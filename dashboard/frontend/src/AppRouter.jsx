import React from 'react'
import App from './App.jsx'
import RadarPage from './pages/RadarPage.jsx'
import ReplayPage from './pages/ReplayPage.jsx'

// Load the vector page lazily so three.js stays out of the other pages' bundle.
const VectorSpacePage = React.lazy(() => import('./pages/VectorSpacePage.jsx'))

/** Render the page for the supplied pathname, defaulting to the dashboard. */
export default function AppRouter({ route }) {
  if (route === '/vectordb') {
    return (
      <React.Suspense fallback={<div>LOADING VECTOR SPACE…</div>}>
        <VectorSpacePage />
      </React.Suspense>
    )
  }
  if (route === '/radar') return <RadarPage />
  if (route === '/replay') return <ReplayPage />
  return <App />
}
