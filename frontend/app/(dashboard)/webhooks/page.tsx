'use client'

import { useState } from 'react'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { Webhook, Plus, Trash2, Send, X, Copy, CheckCircle2, XCircle } from 'lucide-react'
import { webhooksApi } from '@/lib/api'

interface Hook {
  id: string; url: string; events: string[]; active: boolean; description?: string
  last_status?: number | null; last_fired_at?: string | null; failure_count: number; has_secret: boolean
}

function AddModal({ events, onClose, onDone }: { events: string[]; onClose: () => void; onDone: () => void }) {
  const [url, setUrl] = useState('')
  const [desc, setDesc] = useState('')
  const [all, setAll] = useState(true)
  const [sel, setSel] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [secret, setSecret] = useState('')

  const toggle = (e: string) => setSel((p) => (p.includes(e) ? p.filter((x) => x !== e) : [...p, e]))

  async function save() {
    if (!url.startsWith('http')) { toast.error('أدخل رابطًا صحيحًا (http/https)'); return }
    setLoading(true)
    try {
      const r = await webhooksApi.create({ url: url.trim(), events: all ? ['*'] : sel, description: desc || undefined })
      setSecret(r.data?.secret || '')
      toast.success('تم إنشاء الويب هوك')
      onDone()
      if (!r.data?.secret) onClose()
    } catch (e: unknown) { const err = e as { response?: { data?: { detail?: string } } }; toast.error(err?.response?.data?.detail || 'فشل') }
    finally { setLoading(false) }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 w-full max-w-md space-y-3 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-white font-cairo">إضافة ويب هوك</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-white"><X size={18} /></button>
        </div>

        {secret ? (
          <div className="space-y-3">
            <p className="text-sm text-gray-300 font-cairo">احفظ هذا المفتاح السري — لن يظهر مرة أخرى. يُستخدم للتحقق من التوقيع (X-Qualifay-Signature).</p>
            <div className="flex items-center gap-2 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2">
              <code className="text-xs text-gold-primary break-all flex-1" dir="ltr">{secret}</code>
              <button onClick={() => { navigator.clipboard.writeText(secret); toast.success('تم النسخ') }} className="text-gray-400 hover:text-white"><Copy size={14} /></button>
            </div>
            <button onClick={onClose} className="w-full py-2.5 rounded-lg bg-gold-primary text-gray-950 font-semibold text-sm font-cairo">تم</button>
          </div>
        ) : (
          <>
            <div>
              <label className="block text-xs text-gray-400 font-cairo mb-1">رابط الويب هوك (n8n / Zapier)</label>
              <input value={url} onChange={(e) => setUrl(e.target.value)} dir="ltr" placeholder="https://n8n.example.com/webhook/..."
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 font-cairo mb-1">الوصف (اختياري)</label>
              <input value={desc} onChange={(e) => setDesc(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo" />
            </div>
            <label className="flex items-center gap-2 text-sm text-gray-300 font-cairo">
              <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} className="accent-gold-primary" /> كل الأحداث
            </label>
            {!all && (
              <div className="flex flex-wrap gap-1.5">
                {events.map((e) => (
                  <button key={e} onClick={() => toggle(e)} type="button"
                    className={clsx('text-[11px] px-2 py-1 rounded-full border font-mono', sel.includes(e) ? 'bg-gold-primary/15 border-gold-primary/40 text-gold-primary' : 'border-gray-700 text-gray-400')}>{e}</button>
                ))}
              </div>
            )}
            <div className="flex gap-2 pt-2">
              <button onClick={onClose} className="flex-1 py-2.5 rounded-lg border border-gray-700 text-gray-400 text-sm font-cairo">إلغاء</button>
              <button onClick={save} disabled={loading} className="flex-1 py-2.5 rounded-lg bg-gold-primary text-gray-950 font-semibold text-sm disabled:opacity-50 font-cairo">{loading ? '...' : 'حفظ'}</button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default function WebhooksPage() {
  const { data, mutate, isLoading } = useSWR('webhooks', () => webhooksApi.list().then((r) => r.data))
  const { data: ev } = useSWR('webhook-events', () => webhooksApi.events().then((r) => r.data?.events || []))
  const hooks: Hook[] = Array.isArray(data) ? data : []
  const [adding, setAdding] = useState(false)

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); toast.success(ok); mutate() }
    catch (e: unknown) { const err = e as { response?: { data?: { detail?: string } } }; toast.error(err?.response?.data?.detail || 'فشل') }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white font-cairo flex items-center gap-2"><Webhook size={22} /> الويب هوك</h1>
          <p className="text-gray-400 text-sm mt-1">أرسل أحداث Qualifay إلى n8n أو Zapier أو أي رابط مخصص</p>
        </div>
        <button onClick={() => setAdding(true)} className="flex items-center gap-1.5 bg-gold-primary text-gray-950 font-semibold text-sm px-4 py-2 rounded-lg font-cairo">
          <Plus size={16} /> إضافة
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" /></div>
      ) : hooks.length === 0 ? (
        <div className="text-center py-16 text-gray-500 font-cairo">لا توجد ويب هوك بعد. أضف رابط n8n لبدء الأتمتة.</div>
      ) : (
        <div className="space-y-2">
          {hooks.map((h) => (
            <div key={h.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex items-center gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <code className="text-sm text-white truncate" dir="ltr">{h.url}</code>
                  {h.last_status != null && (
                    <span className={clsx('inline-flex items-center gap-0.5 text-[11px]', h.last_status >= 200 && h.last_status < 300 ? 'text-green-400' : 'text-red-400')}>
                      {h.last_status >= 200 && h.last_status < 300 ? <CheckCircle2 size={12} /> : <XCircle size={12} />}{h.last_status || 'خطأ'}
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-1 mt-1.5">
                  {(h.events || []).map((e) => (
                    <span key={e} className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-400 font-mono">{e}</span>
                  ))}
                </div>
                {h.description && <div className="text-xs text-gray-500 mt-1 font-cairo">{h.description}</div>}
              </div>
              <label className="flex items-center gap-1 text-xs text-gray-400 font-cairo cursor-pointer">
                <input type="checkbox" checked={h.active} onChange={() => act(() => webhooksApi.update(h.id, { active: !h.active }), 'تم')} className="accent-gold-primary" /> مفعّل
              </label>
              <button onClick={() => act(() => webhooksApi.test(h.id), 'تم إرسال حدث تجريبي')} title="اختبار" className="text-gray-400 hover:text-gold-primary"><Send size={15} /></button>
              <button onClick={() => { if (confirm('حذف الويب هوك؟')) act(() => webhooksApi.remove(h.id), 'تم الحذف') }} className="text-gray-500 hover:text-red-400"><Trash2 size={15} /></button>
            </div>
          ))}
        </div>
      )}

      {adding && <AddModal events={ev || []} onClose={() => setAdding(false)} onDone={mutate} />}
    </div>
  )
}
