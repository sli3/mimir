import ReactDOM from 'react-dom/client'
import AppRouter from './AppRouter.jsx'
import './theme/cyberpunk.css'

const root = document.getElementById('root')

ReactDOM.createRoot(root).render(
  <AppRouter route={window.location.pathname} />
)
