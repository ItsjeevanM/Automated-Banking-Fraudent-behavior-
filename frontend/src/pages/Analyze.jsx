import { useState } from 'react'
import CashflowDashboard from '../components/CashflowDashboard'
import UploadBox     from '../components/UploadBox'
import SummaryCards  from '../components/SummaryCards'
import RiskCard      from '../components/RiskCard'
import AIReport      from '../components/AIReport'
import {
  DebitCreditChart,
  SpendingTrendsChart,
  MerchantChart,
  TransactionTypeChart,
} from '../components/Charts'
import { uploadAndAnalyze } from '../services/api'

// ── Analysis state machine ─────────────────────────────────────────────────
// 'idle'    → State A: upload only
// 'loading' → State B: upload + spinner
// 'done'    → State C: upload + full results

export default function Analyze() {
  const [phase,   setPhase]   = useState('idle')     // 'idle' | 'loading' | 'done'
  const [results, setResults] = useState(null)
  const [error,   setError]   = useState(null)

  const handleUpload = async (file) => {
    setPhase('loading')
    setError(null)
    try {
      const data = await uploadAndAnalyze(file)
      setResults(data)
      setPhase('done')
      // Smooth-scroll to results after a tick
      setTimeout(() => document.getElementById('results-section')?.scrollIntoView({ behavior:'smooth' }), 100)
    } catch (err) {
      setError(err.message ?? 'Analysis failed. Please try again.')
      setPhase('idle')
    }
  }

  const handleReset = () => {
    setPhase('idle')
    setResults(null)
    setError(null)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <section className="min-h-screen" style={{ padding:'120px 48px 80px', background:'var(--bg2)', borderTop:'1px solid var(--border)' }}>

      {/* ── Page header ── */}
      <p className="section-label">Analyze Now</p>
      <h2 style={{ fontFamily:'Syne, sans-serif', fontWeight:800, fontSize:'clamp(2rem,4vw,3.2rem)', letterSpacing:'-0.03em', marginBottom:16, lineHeight:1.1 }}>
        Upload & Get Results
      </h2>
      <p className="leading-relaxed max-w-xl mb-16" style={{ color:'var(--muted)', fontWeight:300 }}>
        Drop a statement and receive a complete forensic analysis — risk score, flagged transactions, and an evidence-ready report — within seconds.
      </p>

      {/* ═══════════════════════════════════════════
          STATE A + B  ─  Upload section (always visible)
      ══════════════════════════════════════════════ */}
      <div className="grid gap-12 mb-16" style={{ gridTemplateColumns:'1fr 1fr', alignItems:'start' }}>
        {/* Upload box */}
        <UploadBox onUpload={handleUpload} loading={phase === 'loading'} />

        {/* Right info panel (shown while idle / loading) */}
        {phase !== 'done' && (
          <div className="flex flex-col gap-5">
            {/* Processing steps */}
            <div className="card p-6">
              <p className="mb-4" style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'0.7rem', color:'var(--muted)', textTransform:'uppercase', letterSpacing:'0.06em' }}>
                What happens after upload
              </p>
              {[
                { n:'01', label:'OCR & Field Extraction',  active: phase === 'loading' },
                { n:'02', label:'Data Cleaning & Standardization', active: false },
                { n:'03', label:'Risk Scoring (0–100)',    active: false },
                { n:'04', label:'Anomaly Detection',       active: false },
                { n:'05', label:'AI Report Generation',    active: false },
              ].map(({ n, label, active }) => (
                <div key={n} className="flex items-center gap-3 py-3" style={{ borderBottom:'1px solid rgba(255,255,255,.04)' }}>
                  <span
                    className="flex items-center justify-center rounded-md text-xs font-bold shrink-0"
                    style={{ width:28, height:28, background: active ? 'rgba(0,212,170,.15)' : 'var(--surface2)', fontFamily:'JetBrains Mono, monospace', color: active ? 'var(--teal)' : 'var(--muted)', border: active ? '1px solid rgba(0,212,170,.3)' : '1px solid transparent' }}
                  >
                    {n}
                  </span>
                  <span className="text-sm" style={{ color: active ? 'var(--text)' : 'var(--muted)' }}>{label}</span>
                  {active && <span className="spinner ml-auto" style={{ width:14, height:14 }} />}
                </div>
              ))}
            </div>

            {/* Error */}
            {error && (
              <div className="card p-4 flex items-start gap-3" style={{ border:'1px solid rgba(239,68,68,.3)', background:'rgba(239,68,68,.05)' }}>
                <span className="text-xl">⚠️</span>
                <p className="text-sm" style={{ color:'#ef4444' }}>{error}</p>
              </div>
            )}
          </div>
        )}

        {/* Right: quick result summary card (while done) */}
        {phase === 'done' && results && (
          <div className="flex flex-col gap-4">
            <div className="card p-5 flex flex-col gap-3">
              <p style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'0.7rem', color:'var(--teal)', textTransform:'uppercase', letterSpacing:'0.06em' }}>Analysis Complete</p>
              <div className="flex items-end gap-3">
                <span style={{ fontFamily:'Syne, sans-serif', fontSize:'3rem', fontWeight:800, color:'var(--amber)', lineHeight:1 }}>
                  {results.risk.riskScore.toFixed(1)}
                </span>
                <span style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'1rem', color:'var(--muted)', marginBottom:4 }}>/ 100</span>
              </div>
              <span className="chip chip-red w-fit">⚠ {results.risk.riskLevel} Risk</span>
              <div className="flex justify-between text-sm py-2 px-3 rounded-lg" style={{ background:'rgba(239,68,68,.05)', border:'1px solid rgba(239,68,68,.15)' }}>
                <span style={{ color:'var(--muted)' }}>Flagged Transactions</span>
                <span style={{ fontFamily:'JetBrains Mono, monospace', color:'#ef4444', fontWeight:600 }}>{results.risk.flaggedCount} / {results.risk.totalCount}</span>
              </div>
            </div>
            <button className="btn-ghost text-sm" onClick={handleReset}>↺ Analyse another file</button>
          </div>
        )}
      </div>

      {/* ═══════════════════════════════════════════
          STATE B  ─  Loading indicator strip
      ══════════════════════════════════════════════ */}
      {phase === 'loading' && (
        <div className="flex items-center justify-center gap-4 py-12 rounded-2xl mb-12"
          style={{ background:'rgba(0,212,170,.04)', border:'1px solid rgba(0,212,170,.12)' }}>
          <div className="spinner w-6 h-6" />
          <p style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'0.82rem', color:'var(--teal)' }}>
            Running analysis pipeline…
          </p>
        </div>
      )}

      {/* ═══════════════════════════════════════════
          STATE C  ─  Results (visible only when done)
      ══════════════════════════════════════════════ */}
      {phase === 'done' && results && (
        <div id="results-section" className="flex flex-col gap-10">

          {/* Divider */}
          <div className="flex items-center gap-4">
            <div className="flex-1 h-px" style={{ background:'var(--border)' }} />
            <p className="section-label mb-0" style={{ marginBottom:0 }}>Analysis Results</p>
            <div className="flex-1 h-px" style={{ background:'var(--border)' }} />
          </div>

          {/* ── KPI cards ── */}
          <SummaryCards summary={results.summary} />

          {/* ── Charts 2×2 ── */}
          <div>
            <p className="section-label mb-5">Data Visualizations</p>
            <div className="grid gap-5" style={{ gridTemplateColumns:'1fr 1fr' }}>
              <DebitCreditChart     data={results.debitCredit}      />
              <SpendingTrendsChart  data={results.spendingTrends}   />
              <MerchantChart        data={results.merchants}         />
              <TransactionTypeChart data={results.transactionTypes} />
            </div>
          </div>
          {/* ── Cash Flow Forecast ── */}
<div>
  <p className="section-label mb-5">Cash Flow Forecast</p>
  <CashflowDashboard data={results.debitCredit} />
</div>
          {/* ── Risk Analysis ── */}
          <div>
            <p className="section-label mb-5">Risk Analysis</p>
            <RiskCard
              riskScore={results.risk.riskScore}
              riskLevel={results.risk.riskLevel}
              flaggedCount={results.risk.flaggedCount}
              totalCount={results.risk.totalCount}
              flaggedTransactions={results.flagged}
            />
          </div>

          {/* ── AI Report ── */}
          <div>
            <p className="section-label mb-5">AI Forensic Report</p>
            <AIReport report={results.aiReport} />
          </div>

        </div>
      )}
    </section>
  )
}
