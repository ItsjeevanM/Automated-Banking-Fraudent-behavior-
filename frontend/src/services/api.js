/**
 * api.js — Real FastAPI data service layer
 *
 * Flow for uploadAndAnalyze:
 *   1. POST /upload          → { job_id, upload_id }
 *   2. Poll GET /jobs/{id}   → wait for status === "done" | "failed"
 *   3. GET /reports/         → grab the latest report_id
 *   4. GET /reports/{id}     → portfolio_summary + episodes + llm_report
 *   5. GET /reports/{id}/transactions → flagged rows
 *   6. Transform → UI shape expected by Analyze.jsx
 */

// ── Config ────────────────────────────────────────────────────────────────────
export const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// ── Auth helpers ──────────────────────────────────────────────────────────────
function authHeaders() {
  const token = localStorage.getItem('access_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function apiFetch(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      ...authHeaders(),
      ...options.headers,
    },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `HTTP ${res.status}`)
  }
  return res.json()
}

// ── Polling helper ────────────────────────────────────────────────────────────
async function pollJob(jobId, onProgress, intervalMs = 1500, timeoutMs = 300_000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const job = await apiFetch(`/jobs/${jobId}`)
    onProgress?.(job)
    if (job.status === 'done')    return job
    if (job.status === 'failed')  throw new Error(job.error_msg ?? 'Analysis job failed')
    await new Promise(r => setTimeout(r, intervalMs))
  }
  throw new Error('Analysis timed out after 5 minutes')
}

// ── Shape converters ──────────────────────────────────────────────────────────
/**
 * Turn the engine's portfolio_summary into SummaryCards-compatible shape.
 */
function toSummary(ps, txns) {
  const debits  = txns.filter(t => t.debit_credit?.toUpperCase().includes('DEBIT'))
  const credits = txns.filter(t => t.debit_credit?.toUpperCase().includes('CREDIT'))

  const totalDebit  = debits.reduce((s, t) => s + (t.amount ?? 0), 0)
  const totalCredit = credits.reduce((s, t) => s + (t.amount ?? 0), 0)

  // top merchant by frequency in flagged set
  const mFreq = {}
  txns.forEach(t => { const m = t.narration ?? t.merchant ?? '?'; mFreq[m] = (mFreq[m] ?? 0) + 1 })
  const topMerchant = Object.entries(mFreq).sort((a, b) => b[1] - a[1])[0]?.[0] ?? 'N/A'

  const amounts = txns.map(t => t.amount ?? 0).filter(Boolean)
  const avg     = amounts.length ? amounts.reduce((s, v) => s + v, 0) / amounts.length : 0
  const max     = amounts.length ? Math.max(...amounts) : 0

  return {
    totalTransactions: ps.total_transactions ?? 0,
    totalDebit:        Math.round(totalDebit),
    totalCredit:       Math.round(totalCredit),
    topMerchant,
    avgTransaction:    Math.round(avg),
    maxTransaction:    Math.round(max),
  }
}

/**
 * Build monthly debit/credit series from flagged transactions.
 * Falls back to a sparse series if dates are missing.
 */
function toDebitCredit(txns) {
  const monthly = {}
  txns.forEach(t => {
    const raw = t.txn_date ?? t.date ?? ''
    const label = raw ? new Date(raw).toLocaleDateString('en-GB', { month: 'short', year: '2-digit' }) : 'Unknown'
    if (!monthly[label]) monthly[label] = { debit: 0, credit: 0 }
    const amt = t.amount ?? 0
    const type = (t.debit_credit ?? '').toUpperCase()
    if (type.includes('CREDIT')) monthly[label].credit += amt
    else                          monthly[label].debit  += amt
  })
  return Object.entries(monthly).map(([month, v]) => ({ month, debit: Math.round(v.debit), credit: Math.round(v.credit) }))
}

/**
 * Build merchant bar-chart data from flagged transactions.
 */
function toMerchants(txns) {
  const byMerchant = {}
  txns.forEach(t => {
    const name = t.narration ?? t.merchant ?? 'UNKNOWN'
    byMerchant[name] = (byMerchant[name] ?? 0) + (t.amount ?? 0)
  })
  return Object.entries(byMerchant)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([merchant, amount]) => ({ merchant, amount: Math.round(amount) }))
}

/**
 * Build transaction-type pie data.
 */
function toTransactionTypes(txns) {
  const counts = {}
  txns.forEach(t => {
    const type = t.dominant_signal ?? t.fraud_type ?? 'OTHER'
    counts[type] = (counts[type] ?? 0) + 1
  })
  const total = txns.length || 1
  return Object.entries(counts).map(([name, count]) => ({ name, value: Math.round(count / total * 100) }))
}

/**
 * Convert the backend's flagged transaction list into the RiskCard shape.
 */
function toFlagged(txns) {
  return txns.map((t, i) => ({
    id:            t.id ?? `tx${String(i).padStart(3, '0')}`,
    date:          t.txn_date ?? t.date ?? '',
    merchant:      t.narration ?? t.merchant ?? '',
    debit_credit:  t.debit_credit ?? 'DEBIT',
    transaction_type: t.dominant_signal ?? t.fraud_type ?? '',
    amount:        t.amount ?? 0,
    riskPoints:    Math.round(t.final_risk_score ?? 0),
    reason:        t.combined_reason ?? '',
  }))
}

/**
 * Convert portfolio summary risk fields into the RiskCard risk prop shape.
 */
function toRisk(ps) {
  const score = ps.avg_final_risk_score ?? ps.max_final_risk_score ?? 0
  let riskLevel = 'Low'
  if (score >= 81) riskLevel = 'Critical'
  else if (score >= 61) riskLevel = 'High'
  else if (score >= 41) riskLevel = 'Medium'

  return {
    riskScore:    parseFloat(score.toFixed(1)),
    riskLevel,
    flaggedCount: ps.flagged_count ?? 0,
    totalCount:   ps.total_transactions ?? 0,
  }
}

/**
 * Convert llm_report text into the AIReport prop shape.
 */
function toAIReport(llmText, ps) {
  // Try to parse sections from the LLM text (best-effort)
  let executiveSummary = llmText ?? ''
  const insights = []
  const recommendations = []

  // Fallback: derive insights from portfolio_summary
  if (!llmText || llmText === 'None' || llmText.startsWith('{')) {
    const rd = ps.risk_distribution ?? {}
    executiveSummary = `Analysis complete. ${ps.total_transactions ?? 0} transactions reviewed. ` +
      `${ps.flagged_count ?? 0} flagged (${(ps.flag_rate_pct ?? 0).toFixed(1)}% flag rate). ` +
      `Average risk score: ${(ps.avg_final_risk_score ?? 0).toFixed(1)}/100. ` +
      `Peak fraud hour: ${ps.peak_fraud_hour >= 0 ? ps.peak_fraud_hour + ':00' : 'N/A'}.`
  }

  // Add rule trigger counts as insights
  const rules = ps.rule_trigger_counts ?? {}
  Object.entries(rules)
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .forEach(([rule, count]) => insights.push(`${rule.replace(/_/g, ' ')}: triggered ${count} times`))

  // Add fraud type breakdown as recommendations
  const ftb = ps.fraud_type_breakdown ?? {}
  Object.entries(ftb)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .forEach(([type, count]) => recommendations.push(`Review ${count} case(s) classified as: ${type}`))

  if (recommendations.length === 0) {
    recommendations.push('No specific fraud types detected. Continue monitoring.')
  }

  return { executiveSummary, insights, recommendations }
}

// ── Main export ───────────────────────────────────────────────────────────────

/**
 * Upload a CSV bank statement and run the unified fraud engine.
 *
 * @param {File} file
 * @param {Function} [onProgress]  - called with job object on each poll
 * @returns Full analysis in the shape expected by Analyze.jsx
 */
export async function uploadAndAnalyze(file, onProgress) {
  // 1. Upload file
  const formData = new FormData()
  formData.append('file', file)

  const uploadRes = await fetch(`${BASE_URL}/upload`, {
    method:      'POST',
    headers:     authHeaders(),
    credentials: 'include',
    body:        formData,
  })

  if (uploadRes.status === 401) throw new Error('Please log in before uploading a statement.')
  if (!uploadRes.ok) {
    const body = await uploadRes.json().catch(() => ({}))
    throw new Error(body.detail ?? `Upload failed (HTTP ${uploadRes.status})`)
  }

  const { job_id } = await uploadRes.json()

  // 2. Poll until done
  await pollJob(job_id, onProgress)

  // 3. Get report list and find the one matching this job
  const reports = await apiFetch('/reports/')
  const report  = reports.find(r => r.job_id === job_id) ?? reports[0]
  if (!report) throw new Error('Analysis complete but no report was found.')

  // 4. Fetch full report detail
  const reportDetail = await apiFetch(`/reports/${report.id}`)

  // 5. Fetch flagged transactions (up to 500)
  let txns = []
  try {
    const txnRes = await apiFetch(`/reports/${report.id}/transactions?limit=500`)
    txns = txnRes.transactions ?? []
  } catch (_) { /* empty */ }

  // 6. Shape into UI format
  const ps = reportDetail.portfolio_summary ?? {}

  const debitCredit    = toDebitCredit(txns)
  const spendingTrends = debitCredit.map(d => ({ month: d.month, spend: d.debit + d.credit }))

  return {
    summary:          toSummary(ps, txns),
    debitCredit,
    spendingTrends,
    merchants:        toMerchants(txns),
    transactionTypes: toTransactionTypes(txns),
    risk:             toRisk(ps),
    flagged:          toFlagged(txns),
    aiReport:         toAIReport(reportDetail.llm_report, ps),
    // Pass through raw engine data for future use
    _episodes:        reportDetail.episodes ?? [],
    _portfolioSummary: ps,
  }
}

/**
 * Fetch a previously analysed report by its report ID.
 */
export async function fetchAnalysis(reportId) {
  const reportDetail = await apiFetch(`/reports/${reportId}`)
  let txns = []
  try {
    const txnRes = await apiFetch(`/reports/${reportId}/transactions?limit=500`)
    txns = txnRes.transactions ?? []
  } catch (_) { /* empty */ }

  const ps = reportDetail.portfolio_summary ?? {}
  const debitCredit = toDebitCredit(txns)

  return {
    summary:          toSummary(ps, txns),
    debitCredit,
    spendingTrends:   debitCredit.map(d => ({ month: d.month, spend: d.debit + d.credit })),
    merchants:        toMerchants(txns),
    transactionTypes: toTransactionTypes(txns),
    risk:             toRisk(ps),
    flagged:          toFlagged(txns),
    aiReport:         toAIReport(reportDetail.llm_report, ps),
  }
}

/**
 * Download scored CSV report.
 */
export async function exportPDF(reportId) {
  const token = localStorage.getItem('access_token')
  const res = await fetch(`${BASE_URL}/reports/${reportId}/download`, {
    headers: authHeaders(),
    credentials: 'include',
  })
  if (!res.ok) { alert('Export failed: ' + res.statusText); return }
  const blob = await res.blob()
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = `fraud_report_${reportId?.slice(0, 8) ?? 'export'}.csv`
  a.click()
  URL.revokeObjectURL(url)
}
