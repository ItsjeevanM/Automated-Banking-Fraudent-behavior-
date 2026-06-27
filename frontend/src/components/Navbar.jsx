import { useState, useEffect } from 'react'
import { NavLink, Link, useNavigate } from 'react-router-dom'

const NAV_LINKS = [
  { to: '/',          label: 'Overview'  },
  { to: '/workflow',  label: 'Workflow'  },
  { to: '/features',  label: 'Features'  },
  { to: '/analyze',   label: 'Analyze'   },
]

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const [isLoggedIn, setIsLoggedIn] = useState(!!localStorage.getItem('access_token'))
  const navigate = useNavigate()

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 30)
    window.addEventListener('scroll', onScroll)
    // Re-check auth state whenever storage changes (cross-tab)
    const onStorage = () => setIsLoggedIn(!!localStorage.getItem('access_token'))
    window.addEventListener('storage', onStorage)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('storage', onStorage)
    }
  }, [])

  const handleLogout = async () => {
    const token = localStorage.getItem('access_token')
    if (token) {
      try {
        await fetch('http://localhost:8000/auth/logout', {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
          credentials: 'include',
        })
      } catch (_) { /* ignore network error */ }
    }
    localStorage.removeItem('access_token')
    setIsLoggedIn(false)
    navigate('/login')
  }

  return (
    <header
      className="fixed top-0 left-0 right-0 z-[100] flex items-center justify-between px-12 transition-all duration-300"
      style={{
        paddingTop:    18,
        paddingBottom: 18,
        background:    scrolled
          ? 'rgba(4,13,26,0.97)'
          : 'linear-gradient(to bottom, rgba(4,13,26,0.95), transparent)',
        backdropFilter: 'blur(14px)',
        borderBottom:   scrolled ? '1px solid var(--border)' : '1px solid transparent',
      }}
    >
      {/* Logo */}
      <Link
        to="/"
        className="flex items-center gap-2.5 no-underline"
        style={{ fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: '1.3rem', letterSpacing: '-0.03em', color: 'var(--text)' }}
      >
        <div
          className="w-8 h-8 flex items-center justify-center rounded-lg text-xs font-bold"
          style={{ background: 'linear-gradient(135deg, var(--teal), #0066ff)', fontFamily: 'JetBrains Mono, monospace', color: '#040d1a' }}
        >
          BF
        </div>
        BankForensiq
      </Link>

      {/* Nav links */}
      <nav className="flex items-center gap-6">
        {NAV_LINKS.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className="text-sm font-medium transition-colors duration-200 no-underline"
            style={({ isActive }) => ({
              fontFamily: 'DM Sans, sans-serif',
              color: isActive ? 'var(--teal)' : 'var(--muted)',
              letterSpacing: '0.02em',
            })}
          >
            {label}
          </NavLink>
        ))}

        {/* Auth controls */}
        {isLoggedIn ? (
          <>
            <Link
              to="/analyze"
              id="nav-upload"
              className="btn-primary no-underline"
              style={{ padding: '8px 20px', fontSize: '0.88rem' }}
            >
              Upload Statement
            </Link>
            <button
              id="nav-logout"
              onClick={handleLogout}
              className="btn-ghost"
              style={{ padding: '8px 18px', fontSize: '0.88rem' }}
            >
              Logout
            </button>
          </>
        ) : (
          <>
            <Link
              to="/login"
              id="nav-login"
              className="no-underline text-sm font-medium"
              style={{ color: 'var(--muted)', fontFamily: 'DM Sans, sans-serif', transition: 'color .2s' }}
              onMouseEnter={e => e.target.style.color = 'var(--text)'}
              onMouseLeave={e => e.target.style.color = 'var(--muted)'}
            >
              Login
            </Link>
            <Link
              to="/register"
              id="nav-register"
              className="btn-primary no-underline"
              style={{ padding: '8px 20px', fontSize: '0.88rem' }}
            >
              Register
            </Link>
          </>
        )}
      </nav>
    </header>
  )
}
