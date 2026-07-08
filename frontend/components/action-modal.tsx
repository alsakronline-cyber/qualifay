'use client'

import { useState } from 'react'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { X, Plus, Trash2, CalendarCheck, ShoppingCart, Phone, FileText } from 'lucide-react'
import { flowsApi } from '@/lib/api'

interface Flow { id: string; name: string; type: string }
interface OrderItem { name: string; qty: number }

const TYPE_ICON: Record<string, React.ReactNode> = {
  booking: <CalendarCheck size={14} />, order: <ShoppingCart size={14} />,
  callback: <Phone size={14} />, quote: <FileText size={14} />, custom: <FileText size={14} />,
}

export default function ActionModal({ conversationId, onClose, onDone }: { conversationId: string; onClose: () => void; onDone: () => void }) {
  const { data } = useSWR('flows', () => flowsApi.list().then((r) => r.data))
  const flows: Flow[] = Array.isArray(data) ? data : []
  const [flowId, setFlowId] = useState('')
  const [dt, setDt] = useState('')
  const [items, setItems] = useState<OrderItem[]>([{ name: '', qty: 1 }])
  const [total, setTotal] = useState('')
  const [notes, setNotes] = useState('')
  const [preferred, setPreferred] = useState('')
  const [saving, setSaving] = useState(false)

  const flow = flows.find((f) => f.id === flowId)

  async function submit() {
    if (!flow) { toast.error('اختر نوع الإجراء'); return }
    let payload: Record<string, unknown> = {}
    if (flow.type === 'booking') { if (!dt) { toast.error('اختر التاريخ والوقت'); return } payload = { datetime: dt, notes } }
    else if (flow.type === 'order') { payload = { items: items.filter((i) => i.name.trim()), total, notes } }
    else if (flow.type === 'callback') payload = { preferred_time: preferred, notes }
    else payload = { notes }

    setSaving(true)
    try {
      const r = await flowsApi.submit({ flow_id: flow.id, conversation_id: conversationId, data: payload })
      toast.success(r.data?.confirmation_sent ? 'تم الحفظ وإرسال التأكيد' : 'تم الحفظ')
      onDone(); onClose()
    } catch { toast.error('فشل الحفظ') } finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl w-full max-w-md p-6 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-white font-cairo">إجراء تحويل</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-white"><X size={18} /></button>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {flows.map((f) => (
            <button key={f.id} onClick={() => setFlowId(f.id)}
              className={clsx('flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg border font-cairo transition-colors',
                flowId === f.id ? 'bg-gold-primary text-gray-950 border-gold-primary font-semibold' : 'bg-gray-800 border-gray-700 text-gray-300 hover:text-white')}>
              {TYPE_ICON[f.type]} {f.name}
            </button>
          ))}
        </div>

        {flow?.type === 'booking' && (
          <div>
            <label className="block text-xs text-gray-400 font-cairo mb-1.5">موعد الحجز</label>
            <input type="datetime-local" value={dt} onChange={(e) => setDt(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary" />
          </div>
        )}

        {flow?.type === 'order' && (
          <div className="space-y-2">
            <label className="block text-xs text-gray-400 font-cairo">عناصر الطلب</label>
            {items.map((it, i) => (
              <div key={i} className="flex gap-2">
                <input value={it.name} onChange={(e) => setItems((s) => s.map((x, idx) => idx === i ? { ...x, name: e.target.value } : x))}
                  placeholder="المنتج" dir="rtl" className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-cairo focus:outline-none focus:ring-1 focus:ring-gold-primary" />
                <input type="number" min={1} value={it.qty} onChange={(e) => setItems((s) => s.map((x, idx) => idx === i ? { ...x, qty: Number(e.target.value) } : x))}
                  className="w-16 bg-gray-800 border border-gray-700 rounded-lg px-2 py-2 text-sm text-white text-center" />
                {items.length > 1 && <button onClick={() => setItems((s) => s.filter((_, idx) => idx !== i))} className="text-gray-500 hover:text-red-400"><Trash2 size={14} /></button>}
              </div>
            ))}
            <button onClick={() => setItems((s) => [...s, { name: '', qty: 1 }])} className="text-xs text-gold-primary flex items-center gap-1 font-cairo"><Plus size={12} /> إضافة عنصر</button>
            <input value={total} onChange={(e) => setTotal(e.target.value)} placeholder="الإجمالي (اختياري)" dir="rtl"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-cairo focus:outline-none focus:ring-1 focus:ring-gold-primary" />
          </div>
        )}

        {flow?.type === 'callback' && (
          <input value={preferred} onChange={(e) => setPreferred(e.target.value)} placeholder="الوقت المفضل للاتصال" dir="rtl"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-cairo focus:outline-none focus:ring-1 focus:ring-gold-primary" />
        )}

        {flow && (
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} dir="rtl" placeholder="ملاحظات (اختياري)"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-cairo resize-none focus:outline-none focus:ring-1 focus:ring-gold-primary" />
        )}

        <div className="flex gap-2">
          <button onClick={onClose} className="px-4 py-2 rounded-lg border border-gray-700 text-gray-400 hover:text-white text-sm font-cairo">إلغاء</button>
          <button onClick={submit} disabled={saving || !flow} className="flex-1 py-2 rounded-lg bg-gold-primary text-gray-950 font-semibold text-sm disabled:opacity-50 font-cairo">
            {saving ? 'جارٍ...' : 'تأكيد وإرسال'}
          </button>
        </div>
      </div>
    </div>
  )
}
