import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'

const TOOLTIP_STYLE = {
  background:   'var(--surface)',
  border:       '1px solid var(--border)',
  borderRadius: 8,
  fontFamily:   'JetBrains Mono, monospace',
  fontSize:     '0.74rem',
  color:        'var(--text)',
}

const COLORS = ['#00d4aa','#3b82f6','#f59e0b','#a78bfa','#ef4444']

const renderCustomLabel = ({ cx, cy, midAngle, innerRadius, outerRadius, percent }) => {
  if (percent < 0.05) return null
  const RADIAN = Math.PI / 180
  const r  = innerRadius + (outerRadius - innerRadius) * 0.5
  const x  = cx + r * Math.cos(-midAngle * RADIAN)
  const y  = cy + r * Math.sin(-midAngle * RADIAN)
  return (
    <text
      x={x} y={y}
      fill="white"
      textAnchor="middle"
      dominantBaseline="central"
      style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem', fontWeight: 600 }}
    >
      {`${(percent * 100).toFixed(0)}%`}
    </text>
  )
}

export default function TransactionTypeChart({ data }) {
  // data: [{ name: 'UPI', value: 46 }, { name: 'NEFT', value: 22 }, ...]
  return (
    <div className="card p-5">
      <p className="section-label">Transaction Type Distribution</p>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            outerRadius={80}
            innerRadius={40}
            dataKey="value"
            labelLine={false}
            label={renderCustomLabel}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="none" />
            ))}
          </Pie>
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={(v, name) => [`${v}%`, name]}
          />
          <Legend
            wrapperStyle={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem', color: 'var(--muted)' }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
