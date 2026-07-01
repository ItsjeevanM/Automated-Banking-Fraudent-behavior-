import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from 'recharts'

const TOOLTIP_STYLE = {
  background:   'var(--surface)',
  border:       '1px solid var(--border)',
  borderRadius: 8,
  fontFamily:   'JetBrains Mono, monospace',
  fontSize:     '0.74rem',
  color:        'var(--text)',
}

export default function SpendingTrendsChart({ data }) {
  // data: [{ month: 'Jul 2023', spend: 48000 }, ...]
  return (
    <div className="card p-5">
      <p className="section-label">Spending Trends</p>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data}>
          <defs>
            <linearGradient id="spendGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="#00d4aa" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#00d4aa" stopOpacity={0}    />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
          <XAxis
            dataKey="month"
            tick={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, fill: 'var(--muted)' }}
            axisLine={false} tickLine={false}
          />
          <YAxis
            tickFormatter={v => `₹${(v / 1000).toFixed(0)}k`}
            tick={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, fill: 'var(--muted)' }}
            axisLine={false} tickLine={false}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={v => [`₹${Number(v).toLocaleString('en-IN')}`, 'Total Spend']}
            cursor={{ stroke: 'var(--teal)', strokeWidth: 1 }}
          />
          <Area
            type="monotone"
            dataKey="spend"
            stroke="#00d4aa"
            strokeWidth={2}
            fill="url(#spendGrad)"
            dot={false}
            activeDot={{ r: 4, fill: '#00d4aa', stroke: 'var(--bg)', strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
