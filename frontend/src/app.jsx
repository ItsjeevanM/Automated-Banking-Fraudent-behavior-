import { Routes, Route, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import Navbar   from './components/Navbar'
import Footer   from './components/Footer'
import Home     from './pages/Home'
import Workflow from './pages/Workflow'
import Features from './pages/Features'
import Analyze  from './pages/Analyze'
import Login    from './pages/Login'
import Register from './pages/Register'

const ROUTES = [
  { path: '/',          label: 'Overview', idx: 1 },
  { path: '/workflow',  label: 'Workflow', idx: 2 },
  { path: '/features',  label: 'Features', idx: 3 },
  { path: '/analyze',   label: 'Analyze',  idx: 4 },
]

export default function App() {
  const location = useLocation()
  useEffect(() => { window.scrollTo(0, 0) }, [location.pathname])

  // Auth pages render full-screen without the shell chrome
  const isAuthPage = ['/login', '/register'].includes(location.pathname)
  if (isAuthPage) {
    return (
      <Routes>
        <Route path="/login"    element={<Login />} />
        <Route path="/register" element={<Register />} />
      </Routes>
    )
  }

  const currentRoute = ROUTES.find(r => r.path === location.pathname) ?? ROUTES[0]

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--bg)' }}>
      <Navbar />

      <main key={location.pathname} className="flex-1 page-enter">
        <Routes>
          <Route path="/"         element={<Home />} />
          <Route path="/workflow" element={<Workflow />} />
          <Route path="/features" element={<Features />} />
          <Route path="/analyze"  element={<Analyze />} />
          <Route path="*"         element={<Home />} />
        </Routes>
      </main>

      <Footer />

      {/* Page dot indicators */}
      <nav
        aria-label="Page navigation"
        className="fixed bottom-6 left-1/2 -translate-x-1/2 flex gap-2 items-center z-50 px-4 py-2 rounded-full"
        style={{ background: 'rgba(4,13,26,0.85)', backdropFilter: 'blur(10px)', border: '1px solid var(--border)' }}
      >
        {ROUTES.map(r => (
          <a
            key={r.path}
            href={r.path}
            title={r.label}
            className="block rounded-full transition-all duration-300"
            style={{
              width:      location.pathname === r.path ? 22 : 7,
              height:     7,
              background: location.pathname === r.path ? 'var(--teal)' : 'rgba(107,130,168,0.4)',
            }}
          />
        ))}
      </nav>

      {/* Page counter chip */}
      <div
        className="fixed bottom-6 right-6 z-50 rounded px-3 py-1"
        style={{
          fontFamily:'JetBrains Mono, monospace', fontSize:'0.64rem',
          color:'var(--muted)', background:'rgba(4,13,26,0.85)',
          backdropFilter:'blur(10px)', border:'1px solid var(--border)',
          textTransform:'uppercase', letterSpacing:'0.06em',
        }}
      >
        {currentRoute.idx} / {ROUTES.length} — {currentRoute.label}
      </div>
    </div>
  )
}
