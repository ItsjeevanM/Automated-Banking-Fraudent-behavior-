import { useState } from 'react'

const WF_STEPS = [
  { icon:'📤', n:1, title:'Upload',     desc:'CSV, PDF, or scanned image — any format accepted'              },
  { icon:'🔍', n:2, title:'Extract',    desc:'OCR & parsing engine pulls all transaction fields'             },
  { icon:'🧹', n:3, title:'Clean',      desc:'Deduplication, missing values, standardization'                },
  { icon:'📊', n:4, title:'Analyze',    desc:'Trends, spending patterns, merchant & anomaly detection'       },
  { icon:'🛡️', n:5, title:'Risk Score', desc:'Rule-based + AI models assign 0–100 risk score'               },
  { icon:'📈', n:6, title:'Visualize',  desc:'Interactive dashboards, timelines, drill-down charts'          },
  { icon:'📄', n:7, title:'Report',     desc:'Court-ready forensic PDF with findings & recommendations'      },
]

const SCHEMA_FIELDS = [
  { name:'id',               type:'uuid',   desc:'Unique transaction identifier'      },
  { name:'debit_credit',     type:'enum',   desc:'DEBIT or CREDIT'                   },
  { name:'amount',           type:'float',  desc:'Transaction value in ₹'            },
  { name:'balance',          type:'float',  desc:'Running account balance'            },
  { name:'date',             type:'date',   desc:'Transaction date (YYYY-MM-DD)'      },
  { name:'time',             type:'time',   desc:'HH:MM:SS timestamp'                 },
  { name:'transaction_type', type:'string', desc:'UPI / NEFT / CARD / ATM'           },
  { name:'merchant',         type:'string', desc:'Payee or merchant name'             },
]

const PREVIEW_ROWS = [
  { type:'DEBIT',  amount:'₹500',    date:'2023-07-26', merchant:'GAS STATION',    dc:'d' },
  { type:'CREDIT', amount:'₹15,000', date:'2024-01-02', merchant:'NEFT/Salary',    dc:'c' },
  { type:'DEBIT',  amount:'₹3,000',  date:'2023-08-22', merchant:'UPI/3234',       dc:'d' },
  { type:'DEBIT',  amount:'₹1,000',  date:'2023-08-07', merchant:'ATM',            dc:'d' },
  { type:'CREDIT', amount:'₹45,000', date:'2023-11-01', merchant:'NEFT/Transfer',  dc:'c' },
]

function StepCard({ icon, n, title, desc }) {
  const [hov, setHov] = useState(false)
  return (
    <div
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      className="flex-1 flex flex-col items-center gap-3 text-center px-3 relative z-10"
    >
      <div
        className="flex items-center justify-center rounded-xl text-xl relative transition-all duration-300"
        style={{
          width: 56, height: 56,
          background:  hov ? 'rgba(0,212,170,.1)' : 'var(--surface)',
          border:      `1px solid ${hov ? 'var(--teal)' : 'var(--border)'}`,
          boxShadow:   hov ? '0 0 20px rgba(0,212,170,.2)' : 'none',
          transform:   hov ? 'translateY(-4px)' : 'none',
        }}
      >
        {icon}
        <span
          className="absolute -top-2 -right-2 flex items-center justify-center rounded-full font-bold"
          style={{ width:20, height:20, background:'var(--teal)', color:'#040d1a', fontFamily:'JetBrains Mono, monospace', fontSize:'0.6rem' }}
        >
          {n}
        </span>
      </div>
      <p style={{ fontFamily:'Syne, sans-serif', fontWeight:700, fontSize:'0.86rem' }}>{title}</p>
      <p className="text-xs leading-relaxed" style={{ color:'var(--muted)' }}>{desc}</p>
    </div>
  )
}

function PreviewRow({ row }) {
  const [hov, setHov] = useState(false)
  return (
    <div
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      className="grid gap-2 px-2.5 py-2 mb-1 rounded-md transition-all duration-200 cursor-default"
      style={{
        gridTemplateColumns: 'repeat(4, 1fr)',
        background: hov ? 'rgba(0,212,170,.05)' : 'rgba(255,255,255,.02)',
        border:     hov ? '1px solid var(--border)' : '1px solid transparent',
      }}
    >
      <span style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'0.7rem', color: row.dc === 'd' ? '#ef4444' : 'var(--teal)' }}>{row.type}</span>
      <span style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'0.7rem' }}>{row.amount}</span>
      <span style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'0.7rem', color:'var(--muted)' }}>{row.date}</span>
      <span style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'0.7rem', color:'var(--muted)' }}>{row.merchant}</span>
    </div>
  )
}

export default function Workflow() {
  return (
    <section className="min-h-screen" style={{ padding:'120px 48px 80px', background:'var(--bg2)', borderTop:'1px solid var(--border)' }}>
      <p className="section-label">System Pipeline</p>
      <h2 style={{ fontFamily:'Syne, sans-serif', fontWeight:800, fontSize:'clamp(2rem,4vw,3.2rem)', letterSpacing:'-0.03em', marginBottom:16, lineHeight:1.1 }}>
        How It Works
      </h2>
      <p className="text-base leading-relaxed max-w-xl mb-16" style={{ color:'var(--muted)', fontWeight:300 }}>
        Seven automated stages transform raw bank statements into structured, risk-scored forensic data — zero manual effort required.
      </p>

      {/* ── Step track ── */}
      <div className="relative">
        <div className="absolute pointer-events-none" style={{ top:28, left:28, right:28, height:1, background:'linear-gradient(to right, var(--teal), transparent)', opacity:.25 }} />
        <div className="flex gap-0">
          {WF_STEPS.map(s => <StepCard key={s.n} {...s} />)}
        </div>
      </div>

      {/* ── Schema + preview ── */}
      <div className="grid gap-10 mt-20" style={{ gridTemplateColumns:'1fr 1fr' }}>
        {/* Schema table */}
        <div className="card overflow-hidden">
          <div className="px-5 py-4 flex items-center gap-2.5" style={{ borderBottom:'1px solid var(--border)', fontFamily:'JetBrains Mono, monospace', fontSize:'0.76rem', color:'var(--teal)' }}>
            <span className="rounded-full w-2 h-2 shrink-0" style={{ background:'var(--teal)' }} />
            transaction_schema.json — Standard Fields
          </div>
          <table className="data-table">
            <thead><tr><th>Field</th><th>Type</th><th>Description</th></tr></thead>
            <tbody>
              {SCHEMA_FIELDS.map(f => (
                <tr key={f.name}>
                  <td style={{ color:'var(--teal)' }}>{f.name}</td>
                  <td style={{ color:'var(--blue)' }}>{f.type}</td>
                  <td style={{ color:'var(--muted)' }}>{f.desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Right col */}
        <div className="flex flex-col gap-5">
          <p className="section-label">Sample Data Preview</p>
          <div className="card p-4">
            <div className="grid gap-2 px-2 py-1.5 mb-2" style={{ gridTemplateColumns:'repeat(4,1fr)' }}>
              {['type','amount','date','merchant'].map(h => (
                <span key={h} style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'0.62rem', color:'var(--muted)', textTransform:'uppercase', letterSpacing:'0.05em' }}>{h}</span>
              ))}
            </div>
            {PREVIEW_ROWS.map((r, i) => <PreviewRow key={i} row={r} />)}
          </div>

          <div className="card p-5">
            <p className="mb-2.5 uppercase tracking-wider" style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'0.66rem', color:'var(--muted)' }}>Auto-Detection</p>
            <p className="text-sm leading-relaxed" style={{ fontWeight:300 }}>
              Columns are matched automatically. Handles{' '}
              <span style={{ color:'var(--teal)' }}>valueDate</span>,{' '}
              <span style={{ color:'var(--teal)' }}>transactionDate</span>,{' '}
              <span style={{ color:'var(--teal)' }}>Debit/Credit</span>, or any bank-specific export format.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
