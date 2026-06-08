/**
 * RiskCard
 * Props:
 *   riskScore          number   0-100
 *   riskLevel          string   'Low' | 'Medium' | 'High' | 'Critical'
 *   flaggedCount       number
 *   totalCount         number
 *   flaggedTransactions array  [{ id, date, merchant, amount, type, reason, riskPoints }]
 */
export default function RiskCard({ riskScore, riskLevel, flaggedCount, totalCount, flaggedTransactions = [] }) {
  const levelColor = {
    Low:      'var(--teal)',
    Medium:   'var(--amber)',
    High:     '#ef4444',
    Critical: '#ef4444',
  }[riskLevel] ?? 'var(--muted)'

  const levelBg = {
    Low:      'rgba(0,212,170,0.12)',
    Medium:   'rgba(245,158,11,0.12)',
    High:     'rgba(239,68,68,0.12)',
    Critical: 'rgba(239,68,68,0.12)',
  }[riskLevel] ?? 'rgba(107,130,168,0.1)'

  const levelBorder = {
    Low:      'rgba(0,212,170,0.25)',
    Medium:   'rgba(245,158,11,0.3)',
    High:     'rgba(239,68,68,0.25)',
    Critical: 'rgba(239,68,68,0.25)',
  }[riskLevel] ?? 'var(--border)'

  const fillPct = Math.min(100, Math.max(0, riskScore))

  // Gradient colour for bar
  const barColor =
    riskScore < 33  ? 'var(--teal)'  :
    riskScore < 66  ? 'var(--amber)' :
    '#ef4444'

  return (
    <div className="flex flex-col gap-5">
      {/* ── Score Header ── */}
      <div className="card p-6 flex flex-col gap-4">
        <p className="section-label" style={{ marginBottom: 0 }}>Risk Analysis</p>

        <div className="flex items-end gap-4">
          <p
            style={{
              fontFamily:    'Syne, sans-serif',
              fontSize:      '4rem',
              fontWeight:    800,
              lineHeight:    1,
              color:         levelColor,
              letterSpacing: '-0.03em',
            }}
          >
            {riskScore.toFixed(1)}
          </p>
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '1.2rem', color: 'var(--muted)', marginBottom: 6 }}>
            / 100
          </span>
        </div>

        {/* Risk level badge */}
        <span
          className="inline-flex items-center gap-1.5 w-fit rounded px-3 py-1 text-xs font-semibold uppercase tracking-wider"
          style={{ fontFamily: 'JetBrains Mono, monospace', background: levelBg, border: `1px solid ${levelBorder}`, color: levelColor }}
        >
          ⚠ {riskLevel} Risk
        </span>

        {/* Score bar */}
        <div className="rounded-full overflow-hidden" style={{ height: 6, background: 'rgba(255,255,255,0.08)' }}>
          <div
            className="h-full rounded-full transition-all duration-1000"
            style={{ width: `${fillPct}%`, background: `linear-gradient(to right, var(--teal), ${barColor})` }}
          />
        </div>

        {/* Flagged count */}
        <div
          className="flex justify-between items-center rounded-lg px-4 py-3 text-sm"
          style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.15)' }}
        >
          <span style={{ color: 'var(--muted)' }}>Flagged Transactions</span>
          <span style={{ fontFamily: 'JetBrains Mono, monospace', color: '#ef4444', fontWeight: 600 }}>
            {flaggedCount} / {totalCount}
          </span>
        </div>
      </div>

      {/* ── Flagged Transactions Table ── */}
      {flaggedTransactions.length > 0 && (
        <div className="card overflow-hidden">
          <div
            className="px-5 py-3.5 flex items-center justify-between"
            style={{ borderBottom: '1px solid var(--border)' }}
          >
            <p style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.74rem', color: 'var(--teal)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Flagged Transactions
            </p>
            <span className="chip chip-red">{flaggedCount} flagged</span>
          </div>

          <div style={{ overflowX: 'auto', maxHeight: 340, overflowY: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Merchant</th>
                  <th>Type</th>
                  <th>Amount</th>
                  <th>Risk Pts</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {flaggedTransactions.map((tx, i) => (
                  <tr key={tx.id ?? i}>
                    <td style={{ color: 'var(--muted)' }}>{tx.date}</td>
                    <td>{tx.merchant}</td>
                    <td>
                      <span className={`chip ${tx.debit_credit === 'DEBIT' ? 'chip-red' : 'chip-teal'}`}>
                        {tx.transaction_type ?? tx.type}
                      </span>
                    </td>
                    <td style={{ color: tx.debit_credit === 'DEBIT' ? '#ef4444' : 'var(--teal)', fontWeight: 600 }}>
                      {tx.debit_credit === 'DEBIT' ? '−' : '+'}₹{Number(tx.amount).toLocaleString('en-IN')}
                    </td>
                    <td>
                      <span className="chip chip-amber">{tx.riskPoints ?? tx.risk_points}</span>
                    </td>
                    <td style={{ color: 'var(--muted)', maxWidth: 240 }}>{tx.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
