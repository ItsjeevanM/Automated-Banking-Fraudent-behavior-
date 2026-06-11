import { useState, useRef } from 'react'

/**
 * UploadBox
 * Props:
 *   onUpload(file) — called with the File object when user selects / drops a file
 *   loading        — bool, shows spinner overlay while analysis runs
 */
export default function UploadBox({ onUpload, loading }) {
  const [dragging, setDragging] = useState(false)
  const [fileName, setFileName] = useState(null)
  const inputRef  = useRef(null)

  const handleFile = (file) => {
    if (!file) return
    setFileName(file.name)
    onUpload(file)
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    handleFile(e.dataTransfer.files?.[0])
  }

  const COLUMN_FIELDS = [
    'id', 'debit_credit', 'amount', 'balance',
    'date', 'time', 'transaction_type', 'merchant',
  ]

  return (
    <div className="flex flex-col gap-5">
      {/* ── Drop Zone ── */}
      <div
        onDragEnter={e => { e.preventDefault(); setDragging(true)  }}
        onDragOver ={e => { e.preventDefault(); setDragging(true)  }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !loading && inputRef.current?.click()}
        className="flex flex-col items-center justify-center text-center gap-4 rounded-2xl cursor-pointer transition-all duration-300 py-14 px-10 select-none"
        style={{
          border:     `2px dashed ${dragging ? 'var(--teal)' : 'rgba(0,212,170,0.25)'}`,
          background: dragging
            ? 'rgba(0,212,170,0.07)'
            : fileName
            ? 'rgba(0,212,170,0.04)'
            : 'rgba(0,212,170,0.02)',
          boxShadow: dragging ? '0 0 32px rgba(0,212,170,0.12)' : 'none',
          opacity:   loading ? 0.6 : 1,
          pointerEvents: loading ? 'none' : 'auto',
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.pdf,.png,.jpg,.jpeg"
          className="hidden"
          onChange={e => handleFile(e.target.files?.[0])}
        />

        {/* Icon */}
        <div className="text-5xl">
          {loading ? '⏳' : fileName ? '✅' : '📂'}
        </div>

        {/* Title */}
        <p style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '1.12rem' }}>
          {loading
            ? 'Analysing statement…'
            : fileName
            ? fileName
            : 'Drop Your Bank Statement'}
        </p>

        {/* Subtitle */}
        <p className="text-sm leading-relaxed max-w-xs" style={{ color: 'var(--muted)' }}>
          {loading
            ? 'Running OCR, cleaning, risk-scoring…'
            : 'Drag & drop your file, or click to browse. Columns are auto-detected and standardized.'}
        </p>

        {/* Format chips */}
        {!loading && (
          <div className="flex gap-2 flex-wrap justify-center">
            {['CSV', 'PDF', 'PNG / JPG'].map(f => (
              <span key={f} className="chip">{f}</span>
            ))}
          </div>
        )}

        {/* CTA button */}
        {!loading && (
          <button
            className="btn-primary mt-1"
            onClick={e => { e.stopPropagation(); inputRef.current?.click() }}
          >
            {fileName ? 'Replace File' : 'Browse Files'}
          </button>
        )}

        {/* Spinner */}
        {loading && (
          <div className="spinner w-8 h-8" />
        )}
      </div>

      {/* ── Column Reference ── */}
      <div className="card p-5">
        <p
          className="uppercase tracking-wider mb-3"
          style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.66rem', color: 'var(--muted)' }}
        >
          Expected CSV Columns
        </p>
        <div className="flex flex-wrap gap-2">
          {COLUMN_FIELDS.map(f => (
            <span key={f} className="chip chip-teal">{f}</span>
          ))}
        </div>
        <p className="mt-3 text-xs leading-relaxed" style={{ color: 'var(--muted)' }}>
          Any variation in column naming is handled automatically.{' '}
          Max file size: <span style={{ color: 'var(--text)' }}>200 MB</span>.
        </p>
      </div>
    </div>
  )
}
