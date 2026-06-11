import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from 'recharts'

const TOOLTIP_STYLE = {
  background:   'var(--surface)',
  border:       '1px solid var(--border)',
  borderRadius: 8,
  fontFamily:   'JetBrains Mono, monospace',
  fontSize:     '0.74rem',
  color:        'var(--text)',
}

export default function DebitCreditChart({ data }) {
  // data: [{ month: 'Jul 2023', debit: 50000, credit: 70000 }, ...]
  return (
    <div className="card p-5">
      <p className="section-label">Debit vs Credit</p>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} barGap={4} barCategoryGap="30%">
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
            formatter={v => [`₹${Number(v).toLocaleString('en-IN')}`, undefined]}
            cursor={{ fill: 'rgba(255,255,255,0.03)' }}
          />
          <Legend
            wrapperStyle={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem', color: 'var(--muted)' }}
          />
          <Bar dataKey="debit"  name="Debit"  fill="#ef4444" radius={[4,4,0,0]} fillOpacity={0.85} />
          <Bar dataKey="credit" name="Credit" fill="#00d4aa" radius={[4,4,0,0]} fillOpacity={0.85} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
