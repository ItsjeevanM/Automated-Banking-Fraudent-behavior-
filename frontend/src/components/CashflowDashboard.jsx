import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

// ── Helpers ───────────────────────────────────────────────────
function fmt(v) {
  if (v == null || isNaN(v)) return "N/A";
  return `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

const RISK_COLORS = {
  LOW:      { bg: "rgba(0,212,170,.12)",  fg: "var(--teal)" },
  MEDIUM:   { bg: "rgba(251,191,36,.12)", fg: "#fbbf24" },
  HIGH:     { bg: "rgba(239,68,68,.12)",  fg: "#ef4444" },
  CRITICAL: { bg: "rgba(239,68,68,.22)",  fg: "#ef4444" },
  UNKNOWN:  { bg: "rgba(148,163,184,.12)", fg: "var(--muted)" },
};

// ── Component ─────────────────────────────────────────────────
export default function CashflowDashboard({ data }) {
  /*
   * `data` is the full cashflow object returned by the backend:
   *   {
   *     metrics:  { current_balance, total_debits, total_credits,
   *                 estimated_daily_spending, median_daily_spending,
   *                 calendar_days, active_debit_days,
   *                 statement_start, statement_end },
   *     forecast: { runway_days, depletion_date, risk_classification,
   *                 projected_balances: [{ day, date, projected_balance }] },
   *     warnings: [string, ...],
   *     metadata: { confidence_level, confidence_reason,
   *                 statement_start, statement_end },
   *   }
   */
  if (!data || !data.metrics) {
    return (
      <div className="card p-6">
        <p style={{ color: "var(--muted)" }}>
          No cashflow data available.
        </p>
      </div>
    );
  }

  const { metrics, forecast, warnings = [], metadata = {} } = data;

  const risk       = (forecast?.risk_classification ?? "UNKNOWN").toUpperCase();
  const riskStyle  = RISK_COLORS[risk] ?? RISK_COLORS.UNKNOWN;
  const projBalances = forecast?.projected_balances ?? [];

  // Chart data: use projected_balances if available, otherwise empty
  const chartData = projBalances.map((p) => ({
    label: p.date ? p.date.slice(0, 7) : `Day ${p.day}`,  // "YYYY-MM"
    balance: p.projected_balance,
  }));

  return (
    <div className="card p-6">
      {/* ── Header ── */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <p
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: "0.7rem",
              color: "var(--teal)",
              textTransform: "uppercase",
              letterSpacing: "0.06em",
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
            90-Day Projection
          </h3>
        </div>

        <span
          className="chip"
          style={{ background: riskStyle.bg, color: riskStyle.fg }}
        >
          {risk.charAt(0) + risk.slice(1).toLowerCase()} Risk
        </span>
      </div>

      {/* ── KPI row ── */}
      <div
        className="grid gap-4 mb-8"
        style={{ gridTemplateColumns: "repeat(3,1fr)" }}
      >
        <div className="card p-4">
          <p style={{ color: "var(--muted)", fontSize: 12 }}>Current Balance</p>
          <h4>{fmt(metrics.current_balance)}</h4>
        </div>

        <div className="card p-4">
          <p style={{ color: "var(--muted)", fontSize: 12 }}>Total Debits</p>
          <h4 style={{ color: "#ef4444" }}>{fmt(metrics.total_debits)}</h4>
        </div>

        <div className="card p-4">
          <p style={{ color: "var(--muted)", fontSize: 12 }}>Total Credits</p>
          <h4 style={{ color: "var(--teal)" }}>{fmt(metrics.total_credits)}</h4>
        </div>

        <div className="card p-4">
          <p style={{ color: "var(--muted)", fontSize: 12 }}>Daily Spend (est.)</p>
          <h4>{fmt(metrics.estimated_daily_spending)}</h4>
        </div>

        <div className="card p-4">
          <p style={{ color: "var(--muted)", fontSize: 12 }}>Runway Days</p>
          <h4
            style={{
              color:
                forecast?.runway_days == null || forecast.runway_days > 90
                  ? "var(--teal)"
                  : forecast.runway_days <= 7
                  ? "#ef4444"
                  : "#fbbf24",
            }}
          >
            {forecast?.runway_days != null ? `${forecast.runway_days} days` : "N/A"}
          </h4>
        </div>

        <div className="card p-4">
          <p style={{ color: "var(--muted)", fontSize: 12 }}>Depletion Date</p>
          <h4 style={{ fontSize: "0.95rem" }}>
            {forecast?.depletion_date ?? "—"}
          </h4>
        </div>
      </div>

      {/* ── Projected Balance Chart ── */}
      {chartData.length > 1 ? (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(255,255,255,0.05)"
              vertical={false}
            />
            <XAxis
              dataKey="label"
              tick={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                fill: "var(--muted)",
              }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tickFormatter={(v) =>
                `₹${(v / 1000).toFixed(0)}k`
              }
              tick={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                fill: "var(--muted)",
              }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                fontFamily: "JetBrains Mono, monospace",
                fontSize: "0.74rem",
                color: "var(--text)",
              }}
              formatter={(v) => [
                `₹${Number(v).toLocaleString("en-IN")}`,
                "Projected Balance",
              ]}
            />
            <ReferenceLine y={0} stroke="rgba(239,68,68,.4)" strokeDasharray="4 4" />
            <Line
              type="monotone"
              dataKey="balance"
              stroke="#00d4aa"
              strokeWidth={3}
              dot={false}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <p style={{ color: "var(--muted)", fontSize: 13, textAlign: "center", padding: "2rem 0" }}>
          Not enough data to draw projection chart.
        </p>
      )}

      {/* ── Warnings ── */}
      {warnings.length > 0 && (
        <div className="mt-6 flex flex-col gap-2">
          {warnings.map((w, i) => (
            <div
              key={i}
              className="flex items-start gap-2 p-3 rounded-lg text-sm"
              style={{
                background: "rgba(251,191,36,.07)",
                border: "1px solid rgba(251,191,36,.2)",
                color: "#fbbf24",
                fontFamily: "JetBrains Mono, monospace",
                fontSize: "0.72rem",
              }}
            >
              <span>⚠</span>
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Confidence footer ── */}
      {metadata.confidence_reason && (
        <p
          style={{
            marginTop: 12,
            fontSize: "0.68rem",
            color: "var(--muted)",
            fontFamily: "JetBrains Mono, monospace",
          }}
        >
          {metadata.confidence_reason}
        </p>
      )}
    </div>
  );
}