'use client'

import { useState, useEffect, useMemo, useCallback } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import toast from 'react-hot-toast'
import { Plus, Trash2, Save, ArrowRightLeft, Printer, ArrowRight } from 'lucide-react'
import { salesApi } from '@/lib/api'
import { DOC_LABEL, STATUS_LABEL } from '../page'

interface Line { description: string; quantity: number; unit_price: number; discount_pct: number; line_total?: number }
interface Form {
  doc_type: string; status: string; currency: string; tax_rate: number
  discount_type: string; discount_value: number
  customer_name: string; customer_company: string; customer_email: string
  customer_phone: string; customer_address: string; customer_tax_id: string
  issue_date: string; due_date: string; notes: string; terms: string; lines: Line[]
}

const BLANK: Form = {
  doc_type: 'quotation', status: 'draft', currency: 'EGP', tax_rate: 14,
  discount_type: 'amount', discount_value: 0,
  customer_name: '', customer_company: '', customer_email: '', customer_phone: '',
  customer_address: '', customer_tax_id: '', issue_date: '', due_date: '', notes: '', terms: '',
  lines: [{ description: '', quantity: 1, unit_price: 0, discount_pct: 0 }],
}
const CONVERT_NEXT: Record<string, string> = { inquiry: 'quotation', quotation: 'sales_order', sales_order: 'invoice' }
const round2 = (n: number) => Math.round(n * 100) / 100

function calc(lines: Line[], dType: string, dVal: number, tax: number) {
  let subtotal = 0
  for (const l of lines) subtotal += (Number(l.quantity) || 0) * (Number(l.unit_price) || 0) * (1 - (Number(l.discount_pct) || 0) / 100)
  subtotal = round2(subtotal)
  let discount = dType === 'percent' ? subtotal * (Number(dVal) || 0) / 100 : (Number(dVal) || 0)
  discount = round2(Math.max(0, Math.min(discount, subtotal)))
  const taxable = round2(subtotal - discount)
  const taxTotal = round2(taxable * (Number(tax) || 0) / 100)
  return { subtotal, discount, taxTotal, grand: round2(taxable + taxTotal) }
}

export default function DocEditor() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const qs = useSearchParams()
  const isNew = id === 'new'
  const [form, setForm] = useState<Form>({ ...BLANK, doc_type: qs.get('type') || 'quotation' })
  const [number, setNumber] = useState('')
  const [loading, setLoading] = useState(!isNew)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (isNew) return
    salesApi.get(id).then((r) => {
      const d = r.data
      setNumber(d.number)
      setForm({
        doc_type: d.doc_type, status: d.status, currency: d.currency || 'EGP', tax_rate: d.tax_rate ?? 14,
        discount_type: d.discount_type || 'amount', discount_value: d.discount_value || 0,
        customer_name: d.customer_name || '', customer_company: d.customer_company || '',
        customer_email: d.customer_email || '', customer_phone: d.customer_phone || '',
        customer_address: d.customer_address || '', customer_tax_id: d.customer_tax_id || '',
        issue_date: d.issue_date ? d.issue_date.slice(0, 10) : '', due_date: d.due_date ? d.due_date.slice(0, 10) : '',
        notes: d.notes || '', terms: d.terms || '',
        lines: (d.lines || []).map((l: Line) => ({ description: l.description, quantity: l.quantity, unit_price: l.unit_price, discount_pct: l.discount_pct })),
      })
    }).catch(() => toast.error('تعذّر تحميل المستند')).finally(() => setLoading(false))
  }, [id, isNew])

  const set = useCallback(<K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => ({ ...f, [k]: v })), [])
  const setLine = (i: number, patch: Partial<Line>) => setForm((f) => ({ ...f, lines: f.lines.map((l, j) => j === i ? { ...l, ...patch } : l) }))
  const addLine = () => setForm((f) => ({ ...f, lines: [...f.lines, { description: '', quantity: 1, unit_price: 0, discount_pct: 0 }] }))
  const delLine = (i: number) => setForm((f) => ({ ...f, lines: f.lines.filter((_, j) => j !== i) }))

  const totals = useMemo(() => calc(form.lines, form.discount_type, form.discount_value, form.tax_rate), [form])

  async function save() {
    if (!form.lines.some((l) => l.description.trim())) return toast.error('أضف بنداً واحداً على الأقل')
    setSaving(true)
    try {
      const payload = { ...form, lines: form.lines.filter((l) => l.description.trim()) }
      if (isNew) {
        const r = await salesApi.create(payload)
        toast.success('تم الحفظ')
        router.replace(`/documents/${r.data.id}`)
      } else {
        await salesApi.update(id, payload)
        toast.success('تم تحديث المستند')
      }
    } catch { toast.error('فشل الحفظ') } finally { setSaving(false) }
  }

  async function convert() {
    try {
      const r = await salesApi.convert(id)
      toast.success(`تم التحويل إلى ${DOC_LABEL[r.data.doc_type]}`)
      router.push(`/documents/${r.data.id}`)
    } catch (e: unknown) { toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'فشل التحويل') }
  }

  async function remove() {
    if (!window.confirm('حذف هذا المستند نهائياً؟')) return
    try { await salesApi.remove(id); toast.success('تم الحذف'); router.push('/documents') }
    catch { toast.error('فشل الحذف') }
  }

  if (loading) return <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" /></div>

  const inp = 'w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo'
  const dueLabel = form.doc_type === 'quotation' ? 'صالح حتى' : form.doc_type === 'invoice' ? 'تاريخ الاستحقاق' : 'التاريخ المطلوب'

  return (
    <div className="space-y-5 max-w-4xl">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <Link href="/documents" className="flex items-center gap-1 text-sm text-gray-400 hover:text-white font-cairo"><ArrowRight size={15} /> المستندات</Link>
        <div className="flex items-center gap-2 flex-wrap">
          {!isNew && (
            <Link href={`/doc-print/${id}`} target="_blank"
              className="flex items-center gap-1.5 border border-gray-700 text-gray-200 hover:bg-gray-800 text-sm px-3 py-2 rounded-lg font-cairo"><Printer size={15} /> طباعة / PDF</Link>
          )}
          {!isNew && CONVERT_NEXT[form.doc_type] && (
            <button onClick={convert} className="flex items-center gap-1.5 border border-gold-primary/40 text-gold-primary hover:bg-gold-primary/10 text-sm px-3 py-2 rounded-lg font-cairo">
              <ArrowRightLeft size={15} /> تحويل إلى {DOC_LABEL[CONVERT_NEXT[form.doc_type]]}</button>
          )}
          {!isNew && <button onClick={remove} className="flex items-center gap-1.5 border border-red-500/30 text-red-400 hover:bg-red-500/10 text-sm px-3 py-2 rounded-lg font-cairo"><Trash2 size={15} /> حذف</button>}
          <button onClick={save} disabled={saving} className="flex items-center gap-1.5 bg-gold-primary text-gray-950 font-semibold text-sm px-4 py-2 rounded-lg disabled:opacity-50 font-cairo">
            {saving ? <span className="w-4 h-4 border-2 border-gray-950 border-t-transparent rounded-full animate-spin" /> : <Save size={15} />} حفظ</button>
        </div>
      </div>

      <div>
        <h1 className="text-2xl font-bold text-white font-cairo">{DOC_LABEL[form.doc_type]} {number && <span className="font-mono text-gold-primary text-lg">{number}</span>}</h1>
      </div>

      {/* Header fields */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div><label className="block text-xs text-gray-400 font-cairo mb-1">الحالة</label>
          <select value={form.status} onChange={(e) => set('status', e.target.value)} className={inp}>
            {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select></div>
        <div><label className="block text-xs text-gray-400 font-cairo mb-1">تاريخ الإصدار</label>
          <input type="date" value={form.issue_date} onChange={(e) => set('issue_date', e.target.value)} className={inp} /></div>
        <div><label className="block text-xs text-gray-400 font-cairo mb-1">{dueLabel}</label>
          <input type="date" value={form.due_date} onChange={(e) => set('due_date', e.target.value)} className={inp} /></div>
      </div>

      {/* Customer */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
        <h2 className="text-sm font-bold text-white font-cairo">بيانات العميل</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input placeholder="اسم الشركة" value={form.customer_company} onChange={(e) => set('customer_company', e.target.value)} className={inp} dir="auto" />
          <input placeholder="اسم جهة الاتصال" value={form.customer_name} onChange={(e) => set('customer_name', e.target.value)} className={inp} dir="auto" />
          <input placeholder="البريد الإلكتروني" value={form.customer_email} onChange={(e) => set('customer_email', e.target.value)} className={inp} dir="ltr" />
          <input placeholder="الهاتف" value={form.customer_phone} onChange={(e) => set('customer_phone', e.target.value)} className={inp} dir="ltr" />
          <input placeholder="الرقم الضريبي" value={form.customer_tax_id} onChange={(e) => set('customer_tax_id', e.target.value)} className={inp} dir="ltr" />
          <input placeholder="العنوان" value={form.customer_address} onChange={(e) => set('customer_address', e.target.value)} className={inp} dir="auto" />
        </div>
      </div>

      {/* Line items */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-2">
        <h2 className="text-sm font-bold text-white font-cairo mb-1">البنود</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-gray-400 text-xs font-cairo">
              <tr><th className="text-right pb-1 w-[42%]">الوصف</th><th className="pb-1">الكمية</th><th className="pb-1">سعر الوحدة</th><th className="pb-1">خصم %</th><th className="text-left pb-1">الإجمالي</th><th></th></tr>
            </thead>
            <tbody>
              {form.lines.map((l, i) => {
                const lt = round2((Number(l.quantity) || 0) * (Number(l.unit_price) || 0) * (1 - (Number(l.discount_pct) || 0) / 100))
                return (
                  <tr key={i}>
                    <td className="pr-0 py-1"><input value={l.description} onChange={(e) => setLine(i, { description: e.target.value })} placeholder="وصف البند" className={inp} dir="auto" /></td>
                    <td className="px-1 py-1"><input type="number" value={l.quantity} onChange={(e) => setLine(i, { quantity: parseFloat(e.target.value) || 0 })} className={`${inp} w-16 text-center`} /></td>
                    <td className="px-1 py-1"><input type="number" value={l.unit_price} onChange={(e) => setLine(i, { unit_price: parseFloat(e.target.value) || 0 })} className={`${inp} w-24 text-center`} /></td>
                    <td className="px-1 py-1"><input type="number" value={l.discount_pct} onChange={(e) => setLine(i, { discount_pct: parseFloat(e.target.value) || 0 })} className={`${inp} w-16 text-center`} /></td>
                    <td className="px-1 py-1 text-left text-white font-mono whitespace-nowrap">{lt.toLocaleString()}</td>
                    <td className="pl-0 py-1"><button onClick={() => delLine(i)} className="text-gray-500 hover:text-red-400"><Trash2 size={15} /></button></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <button onClick={addLine} className="flex items-center gap-1 text-sm text-gold-primary hover:underline font-cairo mt-1"><Plus size={14} /> إضافة بند</button>
      </div>

      {/* Totals + discount/tax */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
          <div><label className="block text-xs text-gray-400 font-cairo mb-1">الخصم</label>
            <div className="flex gap-2">
              <select value={form.discount_type} onChange={(e) => set('discount_type', e.target.value)} className={`${inp} w-28`}>
                <option value="amount">مبلغ</option><option value="percent">نسبة %</option>
              </select>
              <input type="number" value={form.discount_value} onChange={(e) => set('discount_value', parseFloat(e.target.value) || 0)} className={inp} />
            </div></div>
          <div className="grid grid-cols-2 gap-2">
            <div><label className="block text-xs text-gray-400 font-cairo mb-1">ضريبة القيمة المضافة %</label>
              <input type="number" value={form.tax_rate} onChange={(e) => set('tax_rate', parseFloat(e.target.value) || 0)} className={inp} /></div>
            <div><label className="block text-xs text-gray-400 font-cairo mb-1">العملة</label>
              <input value={form.currency} onChange={(e) => set('currency', e.target.value)} className={inp} dir="ltr" /></div>
          </div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 font-cairo text-sm space-y-2">
          <div className="flex justify-between text-gray-300"><span>المجموع الفرعي</span><span className="font-mono">{totals.subtotal.toLocaleString()} {form.currency}</span></div>
          <div className="flex justify-between text-gray-300"><span>الخصم</span><span className="font-mono">− {totals.discount.toLocaleString()}</span></div>
          <div className="flex justify-between text-gray-300"><span>ض.ق.م ({form.tax_rate}%)</span><span className="font-mono">{totals.taxTotal.toLocaleString()}</span></div>
          <div className="flex justify-between text-white font-bold text-base border-t border-gray-700 pt-2 mt-1"><span>الإجمالي</span><span className="font-mono text-gold-primary">{totals.grand.toLocaleString()} {form.currency}</span></div>
        </div>
      </div>

      {/* Notes + terms */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div><label className="block text-xs text-gray-400 font-cairo mb-1">ملاحظات</label>
          <textarea rows={3} value={form.notes} onChange={(e) => set('notes', e.target.value)} className={inp} dir="auto" /></div>
        <div><label className="block text-xs text-gray-400 font-cairo mb-1">الشروط والأحكام</label>
          <textarea rows={3} value={form.terms} onChange={(e) => set('terms', e.target.value)} className={inp} dir="auto" /></div>
      </div>
    </div>
  )
}
