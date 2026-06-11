/**
 * SummaryCards — four KPI tiles
 * Props: summary { totalTransactions, totalDebit, totalCredit, topMerchant, avgTransaction, maxTransaction }
 */
export default function SummaryCards({ summary }) {
  const fmt = (n) =>
    typeof n === 'number'
      ? `₹${n.toLocaleString('en-IN')}`
      : n ?? '—'

  const cards = [
    {
      label: 'Total Transactions',
      value: summary.totalTransactions ?? '—',
      icon:  '📋',
      color: 'var(--teal)',
      mono:  true,
    },
    {
      label: 'Total Debit',
      value: fmt(summary.totalDebit),
      icon:  '📤',
      color: '#ef4444',
      mono:  false,
    },
    {
      label: 'Total Credit',
      value: fmt(summary.totalCredit),
      icon:  '📥',
      color: 'var(--teal)',
      mono:  false,
    },
    {
      label: 'Top Merchant',
      value: summary.topMerchant ?? '—',
      icon:  '🏪',
      color: 'var(--amber)',
      mono:  true,
    },
  ]

  return (
    <div className="grid grid-cols-4 gap-4">
      {cards.map(({ label, value, icon, color, mono }) => (
        <div key={label} className="card p-5 flex flex-col gap-3 hover:bg-surface2 transition-colors duration-200">
          <div className="flex items-center justify-between">
            <span className="text-xs uppercase tracking-wider" style={{ fontFamily: 'JetBrains Mono, monospace', color: 'var(--muted)' }}>
              {label}
            </span>
            <span className="text-lg">{icon}</span>
          </div>
          <p
            className="font-bold leading-none"
            style={{
              fontFamily: mono ? 'JetBrains Mono, monospace' : 'Syne, sans-serif',
              fontSize:   '1.55rem',
              color,
              letterSpacing: '-0.02em',
            }}
          >
            {value}
          </p>
        </div>
      ))}
    </div>
  )
}
