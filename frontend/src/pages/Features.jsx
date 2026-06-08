import { useState, useEffect, useRef } from 'react'

const FEATURES = [
  { icon:'🧠', title:'SHAP Explanations',        desc:'Every flagged transaction shows exactly which factors — amount, time, merchant, frequency — drove the risk score.',          tag:'Explainable AI'             },
  { icon:'📉', title:'Confidence Corridors',      desc:'Risk scores arrive with uncertainty bands so analysts know when to trust the model and when to step in.',                   tag:'Uncertainty Quantification' },
  { icon:'🧬', title:'Spending DNA Fingerprint',  desc:'Builds a personalized behavioral baseline per user. Any deviation instantly triggers a targeted alert.',                   tag:'Anomaly Detection'          },
  { icon:'🕐', title:'Circadian Rhythm Detection',desc:'Learns the hours a user never transacts and flags any activity outside their personal time window.',                       tag:'Behavioral AI'              },
  { icon:'📡', title:'Financial Stress Index',    desc:'Detects early distress signals — micro-withdrawals, cash surges, payday loan activity — before they become crises.',      tag:'Predictive'                 },
  { icon:'📝', title:'Forensic Report Generator', desc:'LLM narrates all flagged transactions into a coherent story with a timeline, risk verdict, and action steps.',            tag:'Court-Ready PDF'            },
  { icon:'🔮', title:'Cash Flow Predictor',       desc:'Forecasts daily balances up to 30 days ahead and warns of overdraft risk before it materialises.',                        tag:'Forecasting'                },
  { icon:'🔎', title:'Smurfing Detector',         desc:'Identifies structuring patterns where large amounts are split into smaller transactions to evade reporting thresholds.',  tag:'AML Compliance'             },
  { icon:'🌐', title:'OCR Multi-Format Support',  desc:'Accepts CSV, PDF, and scanned images. Auto field extraction handles any bank\'s export format without configuration.',   tag:'Data Ingestion'             },
]

const METRICS = [
  { name:'Anomaly Detection Recall',      val:'94.2%', w:94 },
  { name:'Smurfing Pattern Accuracy',     val:'91.7%', w:91 },
  { name:'False Positive Rate',           val:'4.1%',  w:4  },
  { name:'OCR Field Extraction Accuracy', val:'98.3%', w:98 },
  { name:'Report Generation Speed',       val:'< 45s', w:88 },
]

function FeatureCell({ icon, title, desc, tag }) {
  const [hov, setHov] = useState(false)
  return (
    <div
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      className="p-8 transition-colors duration-300 cursor-default"
      style={{ background: hov ? 'var(--surface)' : 'var(--bg)' }}
    >
      <div
        className="flex items-center justify-center rounded-xl text-xl mb-5 transition-all duration-300"
        style={{ width:48, height:48, background: hov ? 'rgba(0,212,170,.1)' : 'var(--surface2)' }}
      >
        {icon}
      </div>
      <p className="font-bold mb-2.5" style={{ fontFamily:'Syne, sans-serif', fontSize:'0.96rem' }}>{title}</p>
      <p className="text-sm leading-relaxed mb-4" style={{ color:'var(--muted)', fontWeight:300 }}>{desc}</p>
      <span className="chip chip-teal">{tag}</span>
    </div>
  )
}

export default function Features() {
  const [visible, setVisible] = useState(false)
  const metricsRef = useRef(null)

  useEffect(() => {
    const obs = new IntersectionObserver(
      entries => { if (entries[0].isIntersecting) { setVisible(true); obs.disconnect() } },
      { threshold: 0.3 }
    )
    if (metricsRef.current) obs.observe(metricsRef.current)
    return () => obs.disconnect()
  }, [])

  return (
    <section className="min-h-screen" style={{ padding:'120px 48px 80px', background:'var(--bg)' }}>
      <p className="section-label">Capabilities</p>
      <h2 style={{ fontFamily:'Syne, sans-serif', fontWeight:800, fontSize:'clamp(2rem,4vw,3.2rem)', letterSpacing:'-0.03em', marginBottom:16, lineHeight:1.1 }}>
        Intelligence Built In
      </h2>
      <p className="leading-relaxed max-w-xl mb-16" style={{ color:'var(--muted)', fontWeight:300 }}>
        Eight advanced AI models power every analysis — from explainable risk scoring to smurfing detection.
      </p>

      {/* ── Feature Grid ── */}
      <div
        className="overflow-hidden rounded-2xl"
        style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:1, background:'var(--border)', border:'1px solid var(--border)' }}
      >
        {FEATURES.map(f => <FeatureCell key={f.title} {...f} />)}
      </div>

      {/* ── Metrics strip ── */}
      <div className="grid gap-12 mt-20" style={{ gridTemplateColumns:'1fr 1fr', alignItems:'center' }}>
        <div>
          <p className="section-label">Model Performance</p>
          <h2 style={{ fontFamily:'Syne, sans-serif', fontWeight:800, fontSize:'clamp(1.8rem,3vw,2.6rem)', letterSpacing:'-0.03em', marginBottom:14, lineHeight:1.1 }}>
            Smarter Risk<br/>Detection
          </h2>
          <p className="leading-relaxed text-sm" style={{ color:'var(--muted)', fontWeight:300 }}>
            Each AI component is independently validated on financial transaction datasets covering millions of records across diverse banking formats.
          </p>
        </div>

        <div ref={metricsRef} className="flex flex-col gap-5">
          {METRICS.map(m => (
            <div key={m.name} className="flex flex-col gap-2">
              <div className="flex justify-between items-baseline">
                <span className="text-sm" style={{ color:'var(--muted)' }}>{m.name}</span>
                <span style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'0.8rem', color:'var(--teal)', fontWeight:500 }}>{m.val}</span>
              </div>
              <div className="rounded-full overflow-hidden" style={{ height:3, background:'rgba(255,255,255,.08)' }}>
                <div
                  className="h-full rounded-full transition-all duration-1000"
                  style={{
                    width:      visible ? `${m.w}%` : '0%',
                    background: m.w <= 5 ? 'var(--teal)' : 'linear-gradient(to right, var(--teal), var(--blue))',
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
