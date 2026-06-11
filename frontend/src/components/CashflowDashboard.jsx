import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

export default function CashflowDashboard({ data = [] }) {
  if (!data.length) {
    return (
      <div className="card p-6">
        <p style={{ color: "var(--muted)" }}>
          No cashflow data available.
        </p>
      </div>
    );
  }

  const latest = data[data.length - 1];

  const avgMonthlySpend =
    data.reduce((sum, d) => sum + d.debit, 0) / data.length;

  const avgMonthlyCredit =
    data.reduce((sum, d) => sum + d.credit, 0) / data.length;

  const netFlow = avgMonthlyCredit - avgMonthlySpend;

  const forecast = [];
  let balance = 50000; // demo starting balance

  for (let i = 1; i <= 6; i++) {
    balance += netFlow;

    forecast.push({
      month: `+${i}M`,
      balance: Math.max(0, Math.round(balance)),
    });
  }

  const riskLevel =
    balance < 10000
      ? "Critical"
      : balance < 30000
      ? "High"
      : balance < 60000
      ? "Medium"
      : "Low";

  return (
    <div className="card p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <p
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: "0.7rem",
              color: "var(--teal)",
              textTransform: "uppercase",
            }}
          >
            Cash Flow Forecast
          </p>

          <h3
            style={{
              fontFamily: "Syne, sans-serif",
              fontSize: "1.6rem",
              fontWeight: 700,
            }}
          >
            6 Month Projection
          </h3>
        </div>

        <span
          className="chip"
          style={{
            background:
              riskLevel === "Low"
                ? "rgba(0,212,170,.12)"
                : "rgba(239,68,68,.12)",
            color:
              riskLevel === "Low"
                ? "var(--teal)"
                : "#ef4444",
          }}
        >
          {riskLevel} Risk
        </span>
      </div>

      <div
        className="grid gap-4 mb-8"
        style={{ gridTemplateColumns: "repeat(3,1fr)" }}
      >
        <div className="card p-4">
          <p style={{ color: "var(--muted)", fontSize: 12 }}>
            Avg Monthly Debit
          </p>
          <h4>₹{Math.round(avgMonthlySpend).toLocaleString()}</h4>
        </div>

        <div className="card p-4">
          <p style={{ color: "var(--muted)", fontSize: 12 }}>
            Avg Monthly Credit
          </p>
          <h4>₹{Math.round(avgMonthlyCredit).toLocaleString()}</h4>
        </div>

        <div className="card p-4">
          <p style={{ color: "var(--muted)", fontSize: 12 }}>
            Net Monthly Flow
          </p>
          <h4
            style={{
              color: netFlow >= 0 ? "var(--teal)" : "#ef4444",
            }}
          >
            ₹{Math.round(netFlow).toLocaleString()}
          </h4>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={forecast}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="month" />
          <YAxis />
          <Tooltip />
          <Line
            type="monotone"
            dataKey="balance"
            stroke="#00d4aa"
            strokeWidth={3}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}