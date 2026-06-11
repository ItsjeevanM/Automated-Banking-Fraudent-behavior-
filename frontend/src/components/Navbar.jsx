import { useState, useEffect } from 'react'
import { NavLink, Link } from 'react-router-dom'

const NAV_LINKS = [
  { to: '/',          label: 'Overview'  },
  { to: '/workflow',  label: 'Workflow'  },
  { to: '/features',  label: 'Features'  },
  { to: '/analyze',   label: 'Analyze'   },
]

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 30)
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

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

      {/* Links */}
      <nav className="flex items-center gap-7">
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

        <Link
          to="/analyze"
          className="btn-primary !py-2 !px-5 !text-sm no-underline"
        >
          Upload Statement
        </Link>
      </nav>
    </header>
  )
}
