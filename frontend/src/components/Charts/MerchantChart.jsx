import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  Cell, ResponsiveContainer,
} from 'recharts'

const TOOLTIP_STYLE = {
  background:   'var(--surface)',
  border:       '1px solid var(--border)',
  borderRadius: 8,
  fontFamily:   'JetBrains Mono, monospace',
  fontSize:     '0.74rem',
  color:        'var(--text)',
}

const BAR_COLORS = ['#00d4aa','#3b82f6','#f59e0b','#a78bfa','#ef4444','#22d3ee']

export default function MerchantChart({ data }) {
  // data: [{ merchant: 'NEFT', amount: 210000 }, ...]  (top N merchants)
  return (
    <div className="card p-5">
      <p className="section-label">Top Merchants by Spend</p>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} layout="vertical" barCategoryGap="25%">
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" horizontal={false} />
          <XAxis
            type="number"
            tickFormatter={v => `₹${(v / 1000).toFixed(0)}k`}
            tick={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, fill: 'var(--muted)' }}
            axisLine={false} tickLine={false}
          />
          <YAxis
            dataKey="merchant"
            type="category"
            width={110}
            tick={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, fill: 'var(--muted)' }}
            axisLine={false} tickLine={false}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={v => [`₹${Number(v).toLocaleString('en-IN')}`, 'Spend']}
            cursor={{ fill: 'rgba(255,255,255,0.03)' }}
          />
          <Bar dataKey="amount" radius={[0,4,4,0]}>
            {data.map((_, i) => (
              <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} fillOpacity={0.85} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
