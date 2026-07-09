'use client'

import { useState } from 'react'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { FlaskConical, Plus, Trash2, X, Trophy, Play, Pause } from 'lucide-react'
import { abTestsApi } from '@/lib/api'

interface Variant { id: string; label: string; subject?: string; body: string; sent_count: number; reply_count: number; reply_rate: number }
interface Test { id: string; name: string; channel: string; status: string; variants: Variant[]; total_sent: number; winner_id?: string | null }

const VARS = ['{{name}}', '{{company}}', '{{industry}}', '{{city}}']

function CreateModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [name, setName] = useState('')
  const [channel, setChannel] = useState('whatsapp')
  const [variants, setVariants] = useState([
    { label: 'A', subject: '', body: '' },
    { label: 'B', subject: '', body: '' },
  ])
  const [loading, setLoading] = useState(false)

  const setV = (i: number, k: string, val: string) => setVariants((p) => p.map((v, idx) => (idx === i ? { ...v, [k]: val } : v)))
  const addV = () => setVariants((p) => [...p, { label: String.fromCharCode(65 + p.length), subject: '', body: '' }])

  async function save() {
    if (!name.trim()) { toast.error('أدخل اسم الاختبار'); return }
    if (variants.some((v) => !v.body.trim())) { toast.error('اكتب نص كل نسخة'); return }
    setLoading(true)
    try {
      await abTestsApi.create({ name: name.trim(), channel, variants: variants.map((v) => ({ label: v.label, subject: channel === 'email' ? v.subject : undefined, body: v.body })) })
      toast.success('تم إنشاء الاختبار')
      onDone(); onClose()
    } catch (e: unknown) { const err = e as { response?: { data?: { detail?: string } } }; toast.error(err?.response?.data?.detail || 'فشل') }
    finally { setLoading(false) }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 w-full max-w-lg space-y-3 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-white font-cairo">اختبار A/B جديد</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-white"><X size={18} /></button>
        </div>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="اسم الاختبار"
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo" />
        <div className="flex gap-2">
          {['whatsapp', 'email'].map((c) => (
            <button key={c} onClick={() => setChannel(c)} type="button"
              className={clsx('flex-1 py-2 rounded-lg text-sm border font-cairo', channel === c ? 'bg-gold-primary/15 border-gold-primary/40 text-gold-primary' : 'border-gray-700 text-gray-400')}>
              {c === 'whatsapp' ? 'واتساب' : 'بريد'}
            </button>
          ))}
        </div>
        <div className="text-[11px] text-gray-500 font-cairo">المتغيرات: {VARS.join('  ')}</div>
        {variants.map((v, i) => (
          <div key={i} className="border border-gray-800 rounded-lg p-3 space-y-2">
            <div className="text-xs font-bold text-gold-primary">نسخة {v.label}</div>
            {channel === 'email' && (
              <input value={v.subject} onChange={(e) => setV(i, 'subject', e.target.value)} placeholder="عنوان البريد"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none font-cairo" />
            )}
            <textarea value={v.body} onChange={(e) => setV(i, 'body', e.target.value)} rows={3} placeholder="نص الرسالة..."
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo resize-none" />
          </div>
        ))}
        <button onClick={addV} type="button" className="text-xs text-gold-primary font-cairo">+ إضافة نسخة</button>
        <div className="flex gap-2 pt-2">
          <button onClick={onClose} className="flex-1 py-2.5 rounded-lg border border-gray-700 text-gray-400 text-sm font-cairo">إلغاء</button>
          <button onClick={save} disabled={loading} className="flex-1 py-2.5 rounded-lg bg-gold-primary text-gray-950 font-semibold text-sm disabled:opacity-50 font-cairo">{loading ? '...' : 'إنشاء'}</button>
        </div>
      </div>
    </div>
  )
}

export default function ABTestsPage() {
  const { data, mutate, isLoading } = useSWR('ab-tests', () => abTestsApi.list().then((r) => r.data))
  const tests: Test[] = Array.isArray(data) ? data : []
  const [creating, setCreating] = useState(false)

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); toast.success(ok); mutate() }
    catch (e: unknown) { const err = e as { response?: { data?: { detail?: string } } }; toast.error(err?.response?.data?.detail || 'فشل') }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white font-cairo flex items-center gap-2"><FlaskConical size={22} /> اختبارات A/B</h1>
          <p className="text-gray-400 text-sm mt-1">قارن نسخ الرسائل وتعرّف على الأعلى في معدل الرد</p>
        </div>
        <button onClick={() => setCreating(true)} className="flex items-center gap-1.5 bg-gold-primary text-gray-950 font-semibold text-sm px-4 py-2 rounded-lg font-cairo">
          <Plus size={16} /> اختبار جديد
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" /></div>
      ) : tests.length === 0 ? (
        <div className="text-center py-16 text-gray-500 font-cairo">لا توجد اختبارات بعد. أنشئ اختبارًا لمقارنة نسختين من رسالة التواصل.</div>
      ) : (
        <div className="space-y-3">
          {tests.map((t) => (
            <div key={t.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-3">
                <div className="flex-1">
                  <div className="text-white font-medium font-cairo">{t.name}</div>
                  <div className="text-xs text-gray-500 font-cairo">{t.channel === 'whatsapp' ? 'واتساب' : 'بريد'} · {t.total_sent} رسالة مُرسلة</div>
                </div>
                <span className={clsx('text-[11px] px-2 py-0.5 rounded-full border font-cairo',
                  t.status === 'active' ? 'text-green-400 border-green-500/30 bg-green-500/10' : t.status === 'paused' ? 'text-yellow-400 border-yellow-500/30 bg-yellow-500/10' : 'text-gray-400 border-gray-600 bg-gray-700')}>
                  {t.status === 'active' ? 'نشط' : t.status === 'paused' ? 'متوقف' : 'منتهٍ'}
                </span>
                {t.status === 'active' ? (
                  <button onClick={() => act(() => abTestsApi.update(t.id, { status: 'paused' }), 'تم الإيقاف')} className="text-gray-400 hover:text-yellow-400" title="إيقاف"><Pause size={15} /></button>
                ) : t.status === 'paused' ? (
                  <button onClick={() => act(() => abTestsApi.update(t.id, { status: 'active' }), 'تم التفعيل')} className="text-gray-400 hover:text-green-400" title="تفعيل"><Play size={15} /></button>
                ) : null}
                <button onClick={() => { if (confirm('حذف الاختبار؟')) act(() => abTestsApi.remove(t.id), 'تم الحذف') }} className="text-gray-500 hover:text-red-400"><Trash2 size={15} /></button>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {t.variants.map((v) => {
                  const isWinner = t.winner_id === v.id && t.total_sent > 0 && v.sent_count > 0
                  return (
                    <div key={v.id} className={clsx('rounded-lg border p-3', isWinner ? 'border-gold-primary/50 bg-gold-primary/5' : 'border-gray-800')}>
                      <div className="flex items-center gap-1.5 mb-1">
                        <span className="text-xs font-bold text-gold-primary">نسخة {v.label}</span>
                        {isWinner && <Trophy size={13} className="text-gold-primary" />}
                        <span className="ml-auto text-sm font-bold text-white">{v.reply_rate}%</span>
                      </div>
                      <div className="text-xs text-gray-400 line-clamp-2 font-cairo">{v.body}</div>
                      <div className="text-[11px] text-gray-500 mt-1.5 font-cairo">{v.sent_count} مُرسلة · {v.reply_count} رد</div>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {creating && <CreateModal onClose={() => setCreating(false)} onDone={mutate} />}
    </div>
  )
}
