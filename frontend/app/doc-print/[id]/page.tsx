'use client'

// Standalone (no dashboard chrome) professional A4 view of a sales document, for print / save-as-PDF.
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { salesApi } from '@/lib/api'

const DOC_TITLE: Record<string, { ar: string; en: string }> = {
  inquiry: { ar: 'طلب عرض سعر', en: 'INQUIRY' },
  quotation: { ar: 'عرض سعر', en: 'QUOTATION' },
  sales_order: { ar: 'أمر بيع', en: 'SALES ORDER' },
  invoice: { ar: 'فاتورة', en: 'INVOICE' },
}
interface Line { description: string; quantity: number; unit_price: number; discount_pct: number; line_total: number }
interface Seller { name: string; address?: string; phone?: string; email?: string; website?: string; tax_id?: string }
interface Doc {
  doc_type: string; number: string; status: string; currency: string
  customer_name?: string; customer_company?: string; customer_email?: string; customer_phone?: string
  customer_address?: string; customer_tax_id?: string; issue_date?: string; due_date?: string
  subtotal: number; discount_total: number; tax_rate: number; tax_total: number; grand_total: number
  notes?: string; terms?: string; lines: Line[]; seller?: Seller
}

export default function DocPrint() {
  const { id } = useParams<{ id: string }>()
  const [doc, setDoc] = useState<Doc | null>(null)
  const [err, setErr] = useState(false)

  useEffect(() => {
    salesApi.get(id).then((r) => setDoc(r.data)).catch(() => setErr(true))
  }, [id])

  if (err) return <div style={{ padding: 40, fontFamily: 'sans-serif' }}>تعذّر تحميل المستند.</div>
  if (!doc) return <div style={{ padding: 40, fontFamily: 'sans-serif' }}>...</div>

  const t = DOC_TITLE[doc.doc_type] || { ar: 'مستند', en: 'DOCUMENT' }
  const cur = doc.currency || 'EGP'
  const money = (n: number) => `${(n ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${cur}`
  const dt = (s?: string) => (s ? new Date(s).toLocaleDateString('en-GB') : '—')
  const s = doc.seller || { name: '' }
  const dueLabel = doc.doc_type === 'quotation' ? 'Valid Until' : doc.doc_type === 'invoice' ? 'Due Date' : 'Required Date'

  return (
    <>
      <style>{`
        :root { color-scheme: light; }
        body { background:#f3f4f6; margin:0; }
        .sheet { background:#fff; color:#111827; max-width:800px; margin:24px auto; padding:48px;
          box-shadow:0 4px 24px rgba(0,0,0,.12); font-family:'Cairo','Segoe UI',sans-serif; }
        .row { display:flex; justify-content:space-between; align-items:flex-start; gap:24px; }
        .muted { color:#6b7280; font-size:12px; }
        table { width:100%; border-collapse:collapse; margin-top:8px; }
        th { background:#111827; color:#fff; font-size:12px; padding:9px 10px; text-align:left; }
        th.r, td.r { text-align:right; }
        td { padding:9px 10px; border-bottom:1px solid #e5e7eb; font-size:13px; }
        .tot td { border:none; padding:4px 10px; }
        .noprint { text-align:center; margin:16px; }
        @media print { body { background:#fff; } .sheet { box-shadow:none; margin:0; max-width:none; padding:32px; } .noprint { display:none; } }
      `}</style>
      <div className="noprint">
        <button onClick={() => window.print()} style={{ background: '#111827', color: '#fff', border: 'none', padding: '10px 22px', borderRadius: 8, cursor: 'pointer', fontSize: 14 }}>
          🖨️ طباعة / حفظ PDF
        </button>
      </div>

      <div className="sheet">
        {/* Header: seller + doc title */}
        <div className="row" style={{ borderBottom: '2px solid #111827', paddingBottom: 16 }}>
          <div>
            <div style={{ fontSize: 22, fontWeight: 800 }}>{s.name || '—'}</div>
            <div className="muted" style={{ marginTop: 4, lineHeight: 1.6 }}>
              {s.address && <div>{s.address}</div>}
              {(s.phone || s.email) && <div>{[s.phone, s.email].filter(Boolean).join(' · ')}</div>}
              {s.website && <div>{s.website}</div>}
              {s.tax_id && <div>Tax ID: {s.tax_id}</div>}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 26, fontWeight: 800, letterSpacing: 1 }}>{t.en}</div>
            <div style={{ fontSize: 15 }}>{t.ar}</div>
            <div className="muted" style={{ marginTop: 8, lineHeight: 1.7 }}>
              <div><b>No:</b> {doc.number}</div>
              <div><b>Date:</b> {dt(doc.issue_date)}</div>
              {doc.due_date && <div><b>{dueLabel}:</b> {dt(doc.due_date)}</div>}
            </div>
          </div>
        </div>

        {/* Bill to */}
        <div style={{ marginTop: 20 }}>
          <div className="muted" style={{ fontWeight: 700, marginBottom: 4 }}>BILL TO</div>
          <div style={{ fontWeight: 700, fontSize: 15 }}>{doc.customer_company || doc.customer_name || '—'}</div>
          <div className="muted" style={{ lineHeight: 1.6 }}>
            {doc.customer_company && doc.customer_name && <div>{doc.customer_name}</div>}
            {doc.customer_address && <div>{doc.customer_address}</div>}
            {(doc.customer_phone || doc.customer_email) && <div>{[doc.customer_phone, doc.customer_email].filter(Boolean).join(' · ')}</div>}
            {doc.customer_tax_id && <div>Tax ID: {doc.customer_tax_id}</div>}
          </div>
        </div>

        {/* Line items */}
        <table>
          <thead>
            <tr><th style={{ width: '48%' }}>Description</th><th className="r">Qty</th><th className="r">Unit Price</th><th className="r">Disc%</th><th className="r">Amount</th></tr>
          </thead>
          <tbody>
            {doc.lines.map((l, i) => (
              <tr key={i}>
                <td>{l.description}</td>
                <td className="r">{l.quantity}</td>
                <td className="r">{money(l.unit_price)}</td>
                <td className="r">{l.discount_pct ? `${l.discount_pct}%` : '—'}</td>
                <td className="r">{money(l.line_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Totals */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
          <table style={{ width: 300 }} className="tot">
            <tbody>
              <tr><td className="muted">Subtotal</td><td className="r">{money(doc.subtotal)}</td></tr>
              {doc.discount_total > 0 && <tr><td className="muted">Discount</td><td className="r">− {money(doc.discount_total)}</td></tr>}
              <tr><td className="muted">VAT ({doc.tax_rate}%)</td><td className="r">{money(doc.tax_total)}</td></tr>
              <tr style={{ borderTop: '2px solid #111827' }}>
                <td style={{ fontWeight: 800, fontSize: 15, paddingTop: 8 }}>TOTAL</td>
                <td className="r" style={{ fontWeight: 800, fontSize: 15, paddingTop: 8 }}>{money(doc.grand_total)}</td>
              </tr>
            </tbody>
          </table>
        </div>

        {/* Notes + terms */}
        {(doc.notes || doc.terms) && (
          <div style={{ marginTop: 28, borderTop: '1px solid #e5e7eb', paddingTop: 16 }}>
            {doc.notes && <div style={{ marginBottom: 10 }}><div className="muted" style={{ fontWeight: 700 }}>Notes</div><div style={{ fontSize: 13, whiteSpace: 'pre-wrap' }}>{doc.notes}</div></div>}
            {doc.terms && <div><div className="muted" style={{ fontWeight: 700 }}>Terms &amp; Conditions</div><div style={{ fontSize: 12, whiteSpace: 'pre-wrap', color: '#374151' }}>{doc.terms}</div></div>}
          </div>
        )}

        <div style={{ textAlign: 'center', marginTop: 36, fontSize: 11, color: '#9ca3af' }}>
          Generated by Qualifay · {doc.number}
        </div>
      </div>
    </>
  )
}
