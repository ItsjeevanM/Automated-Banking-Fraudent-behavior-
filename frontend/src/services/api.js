/**
 * api.js — Data service layer
 *
 * All UI components import from here.
 * When FastAPI is ready:
 *   1. Replace MOCK_* constants with real fetch() calls.
 *   2. Update the BASE_URL constant.
 *   3. No changes required in any page or component.
 */

// ── Config ──────────────────────────────────────────────────────────────────
export const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// ── Mock datasets ────────────────────────────────────────────────────────────

const MOCK_SUMMARY = {
  totalTransactions: 985,
  totalDebit:        422090,
  totalCredit:       420571,
  topMerchant:       'NEFT',
  avgTransaction:    855,
  maxTransaction:    45000,
}

const MOCK_DEBIT_CREDIT = [
  { month: 'Jul 23', debit:   270, credit:      0 },
  { month: 'Aug 23', debit: 23000, credit:   8000 },
  { month: 'Sep 23', debit: 48000, credit:  12000 },
  { month: 'Oct 23', debit: 42000, credit:  15000 },
  { month: 'Nov 23', debit: 80000, credit: 150000 },
  { month: 'Dec 23', debit: 46000, credit:  20000 },
  { month: 'Jan 24', debit: 69000, credit:  35000 },
  { month: 'Feb 24', debit:100000, credit:  22000 },
  { month: 'Mar 24', debit:120000, credit:  45000 },
  { month: 'Apr 24', debit: 80000, credit:  30000 },
]

const MOCK_SPENDING_TRENDS = MOCK_DEBIT_CREDIT.map(d => ({
  month: d.month,
  spend: d.debit + d.credit,
}))

const MOCK_MERCHANTS = [
  { merchant: 'NEFT',              amount: 210000 },
  { merchant: 'BY CASH',           amount: 145000 },
  { merchant: 'UPI/23181',         amount: 130000 },
  { merchant: 'UPI/4103',          amount: 130000 },
  { merchant: 'GAS FILL. STATION', amount:  25000 },
  { merchant: 'OTHERS',            amount:  25000 },
]

const MOCK_TX_TYPES = [
  { name: 'UPI',    value: 46 },
  { name: 'NEFT',   value: 22 },
  { name: 'CARD',   value: 18 },
  { name: 'CASH',   value: 10 },
  { name: 'OTHERS', value:  4 },
]

const MOCK_RISK = {
  riskScore:   62.8,
  riskLevel:   'High',
  flaggedCount: 868,
  totalCount:   985,
}

const MOCK_FLAGGED = [
  { id:'tx001', date:'2023-06-27', merchant:'GAS FILLING STATION', debit_credit:'DEBIT', transaction_type:'CARD',   amount:100,   riskPoints:20, reason:'Repeated transaction amount (₹100 appears 39×)' },
  { id:'tx002', date:'2023-06-28', merchant:'GAS FILLING STATION', debit_credit:'DEBIT', transaction_type:'CARD',   amount:170,   riskPoints:20, reason:'Repeated transaction amount (₹170 appears 5×)' },
  { id:'tx003', date:'2023-07-26', merchant:'GAS FILLING STATION', debit_credit:'DEBIT', transaction_type:'CARD',   amount:500,   riskPoints:20, reason:'Repeated transaction amount (₹500 appears 58×)' },
  { id:'tx004', date:'2023-07-31', merchant:'5188810',             debit_credit:'DEBIT', transaction_type:'OTHERS', amount:15,    riskPoints:20, reason:'Repeated transaction amount (₹15 appears 27×)' },
  { id:'tx005', date:'2023-08-07', merchant:'ATM',                 debit_credit:'DEBIT', transaction_type:'ATM',    amount:1000,  riskPoints:20, reason:'Repeated transaction amount (₹1,000 appears 16×)' },
  { id:'tx006', date:'2023-08-22', merchant:'UPI/3234',            debit_credit:'DEBIT', transaction_type:'UPI',    amount:1,     riskPoints:20, reason:'Repeated transaction amount (₹1 appears 27×)' },
  { id:'tx007', date:'2023-08-22', merchant:'UPI/3234',            debit_credit:'DEBIT', transaction_type:'UPI',    amount:3000,  riskPoints:20, reason:'Repeated transaction amount (₹3,000 appears 7×)' },
  { id:'tx008', date:'2023-08-22', merchant:'UPI/32345',           debit_credit:'DEBIT', transaction_type:'UPI',    amount:300,   riskPoints:20, reason:'Repeated transaction amount (₹300 appears 16×)' },
  { id:'tx009', date:'2023-08-23', merchant:'UPI/3235',            debit_credit:'DEBIT', transaction_type:'UPI',    amount:1200,  riskPoints:20, reason:'Repeated transaction amount (₹1,200 appears 4×)' },
  { id:'tx010', date:'2023-08-23', merchant:'UPI/ent',             debit_credit:'DEBIT', transaction_type:'UPI',    amount:400,   riskPoints:20, reason:'Repeated transaction amount (₹400 appears 23×)' },
]

const MOCK_AI_REPORT = {
  executiveSummary:
    'Between May 10 – May 24, the account showed multiple high-risk cash deposits followed by rapid fund transfers to different recipients. This pattern is consistent with layering behaviour. Overall risk level is HIGH. Recommended action: Further investigation and source of funds verification.',
  insights: [
    'Unusual ATM withdrawals detected at irregular hours — 12 AM to 4 AM activity window flagged on 23 occasions.',
    'GAS FILLING STATION appears 58× at ₹500 exactly — structuring pattern suspected.',
    'Rapid fund transfers to 4 distinct UPI IDs within a 24-hour window on 2023-08-22.',
    'Balance shows high volatility: max ₹45,000 followed by near-zero within 3 days.',
    'November 2023 shows a single ₹2,30,000 credit — origin and legitimacy should be verified.',
  ],
  recommendations: [
    'Review and verify source of funds for the November 2023 bulk credit.',
    'Monitor flagged transactions and cross-check UPI recipients against KYC records.',
    'Investigate repeated micro-transactions to 5188810 for potential fee-based laundering.',
    'Apply enhanced due diligence (EDD) given risk score above 60.',
    'File Suspicious Transaction Report (STR) with FIU-IND if investigation confirms fraud.',
  ],
}

// ── Simulated network delay ───────────────────────────────────────────────
const delay = (ms) => new Promise(r => setTimeout(r, ms))

// ── API functions ─────────────────────────────────────────────────────────

/**
 * Upload a bank statement file and retrieve full analysis.
 *
 * REAL IMPLEMENTATION (swap in when FastAPI is ready):
 *
 *   const form = new FormData()
 *   form.append('file', file)
 *   const res  = await fetch(`${BASE_URL}/api/analyze`, { method: 'POST', body: form })
 *   if (!res.ok) throw new Error(await res.text())
 *   return res.json()
 *
 * Expected response shape matches MOCK_ANALYSIS below.
 */
export async function uploadAndAnalyze(file) {
  // Simulate network + processing time
  await delay(2200)

  // In production: return real API response
  return {
    summary:          MOCK_SUMMARY,
    debitCredit:      MOCK_DEBIT_CREDIT,
    spendingTrends:   MOCK_SPENDING_TRENDS,
    merchants:        MOCK_MERCHANTS,
    transactionTypes: MOCK_TX_TYPES,
    risk:             MOCK_RISK,
    flagged:          MOCK_FLAGGED,
    aiReport:         MOCK_AI_REPORT,
  }
}

/**
 * Fetch previously analysed statement by ID.
 * Wire to GET /api/analysis/:id
 */
export async function fetchAnalysis(id) {
  await delay(800)
  return {
    summary:          MOCK_SUMMARY,
    debitCredit:      MOCK_DEBIT_CREDIT,
    spendingTrends:   MOCK_SPENDING_TRENDS,
    merchants:        MOCK_MERCHANTS,
    transactionTypes: MOCK_TX_TYPES,
    risk:             MOCK_RISK,
    flagged:          MOCK_FLAGGED,
    aiReport:         MOCK_AI_REPORT,
  }
}

/**
 * Download forensic PDF report.
 * Wire to GET /api/export-pdf/:id
 */
export async function exportPDF(analysisId) {
  // Real: const res = await fetch(`${BASE_URL}/api/export-pdf/${analysisId}`)
  //       const blob = await res.blob()
  //       saveAs(blob, 'forensic-report.pdf')
  await delay(500)
  alert('PDF export — wire to FastAPI /api/export-pdf endpoint')
}
