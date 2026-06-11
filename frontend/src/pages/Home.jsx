import { useNavigate } from 'react-router-dom'

const txns = [
  { merchant: 'GAS FILLING STATION', meta: '2023-07-26 · CARD',   amount: '−₹500.00',    dc: 'debit'  },
  { merchant: 'UPI/3234',            meta: '2023-08-22 · UPI',    amount: '−₹3,000.00',  dc: 'debit'  },
  { merchant: 'NEFT / Salary',       meta: '2024-01-02 · NEFT',   amount: '+₹15,000.00', dc: 'credit' },
  { merchant: 'ATM / 5188810',       meta: '2023-08-07 · ATM',    amount: '−₹1,000.00',  dc: 'debit'  },
]

const STATS = [
  { v: '0–100', l: 'Risk Score'    },
  { v: '8',     l: 'AI Models'     },
  { v: '3',     l: 'File Formats'  },
  { v: '7',     l: 'Pipeline Steps'},
]

export default function Home() {
  const navigate = useNavigate()

  return (
    <section
      className="relative min-h-screen flex flex-col justify-center overflow-hidden"
      style={{ padding: '140px 48px 80px' }}
    >
      {/* Grid background */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: 'linear-gradient(rgba(0,212,170,.04) 1px, transparent 1px), linear-gradient(90deg, rgba(0,212,170,.04) 1px, transparent 1px)',
          backgroundSize:  '48px 48px',
          WebkitMaskImage: 'radial-gradient(ellipse 80% 60% at 50% 40%, black, transparent)',
        }}
      />
      {/* Orbs */}
      <div className="absolute pointer-events-none rounded-full" style={{ width:580, height:580, background:'rgba(0,212,170,.07)', filter:'blur(80px)', top:-100, right:-100 }} />
      <div className="absolute pointer-events-none rounded-full" style={{ width:380, height:380, background:'rgba(59,130,246,.06)', filter:'blur(80px)', bottom:0, left:'30%' }} />

      {/* ── Badge ── */}
      <div className="anim-fade-up inline-flex items-center gap-2 rounded-full w-fit mb-7 px-3.5 py-1.5"
        style={{ background:'rgba(0,212,170,.1)', border:'1px solid rgba(0,212,170,.25)', fontFamily:'JetBrains Mono, monospace', fontSize:'0.7rem', color:'var(--teal)', letterSpacing:'0.08em', textTransform:'uppercase' }}>
        <span className="anim-pulse rounded-full" style={{ width:7, height:7, background:'var(--teal)' }} />
        AI-Powered Financial Forensics
      </div>

      {/* ── H1 ── */}
      <h1 className="anim-fade-up-d1" style={{ fontFamily:'Syne, sans-serif', fontWeight:800, fontSize:'clamp(2.8rem,6vw,5.5rem)', lineHeight:1, letterSpacing:'-0.04em', maxWidth:820, marginBottom:24 }}>
        Detect <span style={{ color:'var(--teal)' }}>Fraud</span><br/>
        Before It <span style={{ WebkitTextStroke:'2px rgba(0,212,170,.4)', color:'transparent' }}>Hides.</span>
      </h1>

      {/* ── Sub ── */}
      <p className="anim-fade-up-d2 text-lg leading-relaxed max-w-xl mb-10" style={{ color:'var(--muted)', fontWeight:300 }}>
        Automated bank statement analysis that extracts, standardizes, scores risk, and generates court-ready forensic reports — in minutes, not months.
      </p>

      {/* ── CTAs ── */}
      <div className="anim-fade-up-d3 flex gap-3">
        <button className="btn-primary" onClick={() => navigate('/analyze')}>↑ Upload Statement</button>
        <button className="btn-ghost"   onClick={() => navigate('/workflow')}>View Workflow →</button>
      </div>

      {/* ── Stats ── */}
      <div className="anim-fade-up-d4 flex gap-12 mt-16 pt-10" style={{ borderTop:'1px solid var(--border)' }}>
        {STATS.map(({ v, l }) => (
          <div key={l} className="flex flex-col gap-1">
            <span style={{ fontFamily:'Syne, sans-serif', fontSize:'2rem', fontWeight:800, color:'var(--teal)', letterSpacing:'-0.03em' }}>{v}</span>
            <span style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'0.7rem', color:'var(--muted)', textTransform:'uppercase', letterSpacing:'0.06em' }}>{l}</span>
          </div>
        ))}
      </div>

      {/* ── Floating transaction card ── */}
      <div
        className="anim-float anim-fade-in absolute rounded-2xl p-6"
        style={{ right:'5%', top:'50%', transform:'translateY(-50%)', width:375, background:'rgba(10,31,61,.92)', border:'1px solid var(--border)', backdropFilter:'blur(20px)', boxShadow:'0 24px 64px rgba(0,0,0,.4), var(--glow)' }}
      >
        {/* Header */}
        <div className="flex justify-between items-center mb-5">
          <span style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'0.67rem', color:'var(--muted)', textTransform:'uppercase', letterSpacing:'0.08em' }}>// Live Transaction Feed</span>
          <span className="chip chip-red">HIGH RISK</span>
        </div>

        {/* Rows */}
        {txns.map((t, i) => (
          <div key={i} className="flex justify-between items-center py-2.5" style={{ borderBottom: i < txns.length - 1 ? '1px solid rgba(255,255,255,.05)' : 'none' }}>
            <div className="flex flex-col gap-0.5">
              <span className="text-sm font-medium">{t.merchant}</span>
              <span style={{ fontSize:'0.68rem', color:'var(--muted)', fontFamily:'JetBrains Mono, monospace' }}>{t.meta}</span>
            </div>
            <span style={{ fontFamily:'JetBrains Mono, monospace', fontWeight:500, fontSize:'0.86rem', color: t.dc === 'debit' ? '#ef4444' : 'var(--teal)' }}>{t.amount}</span>
          </div>
        ))}

        {/* Score */}
        <div className="mt-4 p-3.5 rounded-xl" style={{ background:'rgba(0,212,170,.05)', border:'1px solid rgba(0,212,170,.15)' }}>
          <div className="flex justify-between items-baseline mb-2">
            <span className="text-xs" style={{ color:'var(--muted)' }}>Overall Risk Score</span>
            <span style={{ fontFamily:'Syne, sans-serif', fontSize:'1.45rem', fontWeight:800, color:'var(--amber)' }}>62.8</span>
          </div>
          <div className="rounded-full overflow-hidden" style={{ height:4, background:'rgba(255,255,255,.1)' }}>
            <div style={{ height:'100%', width:'62.8%', background:'linear-gradient(to right, var(--teal), var(--amber))' }} />
          </div>
        </div>
      </div>
    </section>
  )
}
