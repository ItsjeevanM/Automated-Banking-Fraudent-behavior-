import { Link } from 'react-router-dom'

const LINKS = [
  { to: '/', label: 'Overview' },
  { to: '/workflow', label: 'Workflow' },
  { to: '/features', label: 'Features' },
  { to: '/analyze', label: 'Analyze' },
]

export default function Footer() {
  return (
    <footer
      className="flex items-center justify-between px-12 py-10"
      style={{ borderTop: '1px solid var(--border)', background: 'var(--bg)' }}
    >
      <div>
        <div
          className="flex items-center gap-2.5 mb-2"
          style={{ fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: '1.15rem', letterSpacing: '-0.03em' }}
        >
          <div
            className="w-7 h-7 flex items-center justify-center rounded-md text-xs font-bold"
            style={{ background: 'linear-gradient(135deg, var(--teal), #0066ff)', fontFamily: 'JetBrains Mono, monospace', color: '#040d1a' }}
          >
            BF
          </div>
          BankForensiq
        </div>
        <p style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem', color: 'var(--muted)' }}>
          © 2026 · Jeevan M · Nidhi Mallikarjuna · Hemanth · Tejasvi K S · PES University
        </p>
      </div>

      <nav className="flex items-center gap-6">
        {LINKS.map(({ to, label }) => (
          <Link
            key={to}
            to={to}
            className="no-underline transition-colors duration-200 text-sm"
            style={{ color: 'var(--muted)', fontFamily: 'DM Sans, sans-serif' }}
            onMouseEnter={e => (e.currentTarget.style.color = 'var(--teal)')}
            onMouseLeave={e => (e.currentTarget.style.color = 'var(--muted)')}
          >
            {label}
          </Link>
        ))}
        <a
          href="https://github.com/ItsjeevanM/Automated-Banking-Fraudent-behavior-"
          target="_blank" rel="noreferrer"
          className="no-underline text-sm transition-colors duration-200"
          style={{ color: 'var(--muted)', fontFamily: 'DM Sans, sans-serif' }}
          onMouseEnter={e => (e.currentTarget.style.color = 'var(--teal)')}
          onMouseLeave={e => (e.currentTarget.style.color = 'var(--muted)')}
        >
          GitHub ↗
        </a>
      </nav>
    </footer>
  )
}
