import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

const API = 'http://localhost:8000'

export default function Register() {
  const navigate = useNavigate()
  const [form, setForm]     = useState({ full_name: '', email: '', password: '' })
  const [error, setError]   = useState('')
  const [loading, setLoading] = useState(false)

  const set = (k) => (e) => setForm((p) => ({ ...p, [k]: e.target.value }))

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await fetch(`${API}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail ?? 'Registration failed')
      navigate('/login')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4"
         style={{ background: 'var(--bg)' }}>
      {/* Ambient glow */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div style={{
          position: 'absolute', top: '15%', left: '50%', transform: 'translateX(-50%)',
          width: 500, height: 500, borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(0,212,170,0.07) 0%, transparent 70%)',
        }} />
      </div>

      <div className="w-full max-w-md anim-fade-up">
        {/* Logo / header */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-2 mb-4">
            <span style={{
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: '0.65rem', color: 'var(--teal)',
              background: 'rgba(0,212,170,0.08)',
              border: '1px solid rgba(0,212,170,0.25)',
              padding: '2px 10px', borderRadius: 4,
              textTransform: 'uppercase', letterSpacing: '0.12em',
            }}>BankForensiq</span>
          </div>
          <h1 style={{
            fontFamily: 'Syne, sans-serif', fontWeight: 700,
            fontSize: '1.75rem', color: 'var(--text)',
          }}>
            Create an account
          </h1>
          <p style={{ color: 'var(--muted)', fontSize: '0.88rem', marginTop: 6 }}>
            Start detecting fraud in your bank statements
          </p>
        </div>

        {/* Card */}
        <div style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 16,
          padding: '2rem',
          boxShadow: '0 0 40px rgba(0,212,170,0.06)',
        }}>
          {error && (
            <div style={{
              background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.25)',
              borderRadius: 8, padding: '10px 14px',
              color: '#ef4444', fontSize: '0.84rem', marginBottom: '1.25rem',
            }}>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate>
            {/* Full name */}
            <div style={{ marginBottom: '1.1rem' }}>
              <label style={labelStyle}>Full name</label>
              <input
                id="register-name"
                type="text"
                autoComplete="name"
                required
                value={form.full_name}
                onChange={set('full_name')}
                placeholder="Jane Doe"
                style={inputStyle}
                onFocus={inputFocus}
                onBlur={inputBlur}
              />
            </div>

            {/* Email */}
            <div style={{ marginBottom: '1.1rem' }}>
              <label style={labelStyle}>Email address</label>
              <input
                id="register-email"
                type="email"
                autoComplete="email"
                required
                value={form.email}
                onChange={set('email')}
                placeholder="you@example.com"
                style={inputStyle}
                onFocus={inputFocus}
                onBlur={inputBlur}
              />
            </div>

            {/* Password */}
            <div style={{ marginBottom: '1.5rem' }}>
              <label style={labelStyle}>Password</label>
              <input
                id="register-password"
                type="password"
                autoComplete="new-password"
                required
                minLength={8}
                value={form.password}
                onChange={set('password')}
                placeholder="Min. 8 characters"
                style={inputStyle}
                onFocus={inputFocus}
                onBlur={inputBlur}
              />
            </div>

            <button
              id="register-submit"
              type="submit"
              disabled={loading}
              className="btn-primary"
              style={{ width: '100%', justifyContent: 'center', opacity: loading ? 0.7 : 1 }}
            >
              {loading
                ? <><span className="spinner" style={{ width: 15, height: 15 }} /> Creating account…</>
                : 'Create account'}
            </button>
          </form>
        </div>

        {/* Footer link */}
        <p style={{
          textAlign: 'center', marginTop: '1.25rem',
          color: 'var(--muted)', fontSize: '0.85rem',
        }}>
          Already have an account?{' '}
          <Link to="/login" style={{ color: 'var(--teal)', textDecoration: 'none', fontWeight: 500 }}>
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}

/* ── shared micro-styles ──────────────────────────────── */
const labelStyle = {
  display: 'block',
  color: 'var(--muted)',
  fontSize: '0.78rem',
  fontFamily: 'JetBrains Mono, monospace',
  textTransform: 'uppercase',
  letterSpacing: '0.07em',
  marginBottom: 6,
}

const inputStyle = {
  display: 'block',
  width: '100%',
  padding: '11px 14px',
  background: 'var(--bg2)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  color: 'var(--text)',
  fontSize: '0.92rem',
  fontFamily: 'DM Sans, sans-serif',
  outline: 'none',
  transition: 'border-color 0.2s',
}

function inputFocus(e) {
  e.target.style.borderColor = 'rgba(0,212,170,0.55)'
}
function inputBlur(e) {
  e.target.style.borderColor = 'var(--border)'
}
