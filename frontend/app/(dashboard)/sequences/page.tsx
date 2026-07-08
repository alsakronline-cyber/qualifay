'use client'

import { useState, useCallback } from 'react'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { Plus, GitBranch, Trash2, X, Clock, ArrowDown } from 'lucide-react'
import { sequencesApi, templatesApi, type SeqStep } from '@/lib/api'

interface Seq { id: string; name: string; active: boolean; steps: (SeqStep & { id?: string })[]; stats: Record<string, number> }

const CH = [{ k: 'auto', l: 'تلقائي' }, { k: 'whatsapp', l: 'واتساب' }, { k: 'email', l: 'بريد' }]

function Builder({ initial, templates, onClose, onSaved }: { initial?: Seq; templates: { id: string; name: string }[]; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(initial?.name || '')
  const [active, setActive] = useState(initial?.active ?? true)
  const [steps, setSteps] = useState<SeqStep[]>(initial?.steps?.length ? initial.steps : [{ delay_hours: 0, channel: 'auto', template_id: '', body: '' }])
  const [saving, setSaving] = useState(false)

  const upd = (i: number, patch: Partial<SeqStep>) => setSteps((s) => s.map((st, idx) => idx === i ? { ...st, ...patch } : st))
  const addStep = () => setSteps((s) => [...s, { delay_hours: 24, channel: 'auto', template_id: '', body: '' }])
  const rmStep = (i: number) => setSteps((s) => s.filter((_, idx) => idx !== i))

  async function save() {
    if (!name.trim() || steps.length === 0) { toast.error('أدخل اسماً وخطوة واحدة على الأقل'); return }
    const payload = {
      name, active,
      steps: steps.map((s) => ({
        delay_hours: Number(s.delay_hours) || 0, channel: s.channel,
        template_id: s.template_id || null, subject: s.subject || null, body: s.body || null,
      })),
    }
    setSaving(true)
    try {
      if (initial?.id) await sequencesApi.update(initial.id, payload)
      else await sequencesApi.create(payload)
      toast.success('تم الحفظ'); onSaved(); onClose()
    } catch { toast.error('فشل الحفظ') } finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl w-full max-w-lg max-h-[92vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
          <h3 className="font-semibold text-white font-cairo">{initial?.id ? 'تعديل التسلسل' : 'تسلسل جديد'}</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-white"><X size={18} /></button>
        </div>

        <div className="p-6 space-y-4 overflow-y-auto">
          <div>
            <label className="block text-xs text-gray-400 font-cairo mb-1.5">اسم التسلسل</label>
            <input value={name} onChange={(e) => setName(e.target.value)} dir="rtl"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo" />
          </div>

          <div className="space-y-3">
            {steps.map((s, i) => (
              <div key={i}>
                {i > 0 && (
                  <div className="flex items-center justify-center gap-1 text-[11px] text-gray-500 py-1 font-cairo">
                    <ArrowDown size={12} /> بعد
                    <input type="number" min={0} value={s.delay_hours} onChange={(e) => upd(i, { delay_hours: Number(e.target.value) })}
                      className="w-14 bg-gray-800 border border-gray-700 rounded px-1.5 py-0.5 text-center text-gray-200" /> ساعة
                  </div>
                )}
                <div className="bg-gray-800/60 border border-gray-700 rounded-xl p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-gold-primary font-cairo font-semibold">الخطوة {i + 1}</span>
                    <div className="flex items-center gap-2">
                      <div className="flex gap-0.5 bg-gray-900 rounded-md p-0.5">
                        {CH.map((c) => (
                          <button key={c.k} onClick={() => upd(i, { channel: c.k })}
                            className={clsx('text-[10px] px-2 py-0.5 rounded font-cairo', s.channel === c.k ? 'bg-gold-primary text-gray-950' : 'text-gray-400')}>{c.l}</button>
                        ))}
                      </div>
                      {steps.length > 1 && <button onClick={() => rmStep(i)} className="text-gray-500 hover:text-red-400"><Trash2 size={13} /></button>}
                    </div>
                  </div>
                  <select value={s.template_id || ''} onChange={(e) => upd(i, { template_id: e.target.value })}
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo">
                    <option value="">— نص مخصص —</option>
                    {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </select>
                  {!s.template_id && (
                    <textarea value={s.body || ''} onChange={(e) => upd(i, { body: e.target.value })} rows={2} dir="rtl"
                      placeholder="نص الرسالة... {{name}} {{company}}"
                      className="w-full bg-gray-900 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo resize-none" />
                  )}
                </div>
              </div>
            ))}
            <button onClick={addStep} className="w-full flex items-center justify-center gap-1.5 border border-dashed border-gray-700 hover:border-gray-600 text-gray-400 hover:text-white rounded-xl py-2 text-xs font-cairo transition-colors">
              <Plus size={14} /> إضافة خطوة متابعة
            </button>
          </div>

          <label className="flex items-center gap-2 text-sm text-gray-300 font-cairo">
            <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} className="accent-gold-primary" /> نشط
          </label>
        </div>

        <div className="flex gap-2 px-6 py-4 border-t border-gray-800">
          <button onClick={onClose} className="px-4 py-2 rounded-lg border border-gray-700 text-gray-400 hover:text-white text-sm font-cairo">إلغاء</button>
          <button onClick={save} disabled={saving} className="flex-1 py-2 rounded-lg bg-gold-primary text-gray-950 font-semibold text-sm disabled:opacity-50 font-cairo">{saving ? 'جارٍ...' : 'حفظ التسلسل'}</button>
        </div>
      </div>
    </div>
  )
}

export default function SequencesPage() {
  const { data, mutate, isLoading } = useSWR('sequences', () => sequencesApi.list().then((r) => r.data))
  const sequences: Seq[] = Array.isArray(data) ? data : []
  const { data: tplData } = useSWR('templates', () => templatesApi.list().then((r) => r.data))
  const templates: { id: string; name: string }[] = Array.isArray(tplData) ? tplData : []
  const [editing, setEditing] = useState<Seq | null>(null)
  const [creating, setCreating] = useState(false)

  const del = useCallback(async (id: string) => {
    if (!confirm('حذف هذا التسلسل؟ سيتوقف إرسال المتابعات لمن فيه.')) return
    try { await sequencesApi.remove(id); toast.success('تم الحذف'); mutate() } catch { toast.error('فشل الحذف') }
  }, [mutate])

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white font-cairo">التسلسلات</h1>
          <p className="text-gray-400 text-sm mt-1">Sequences — متابعات تلقائية متعددة الخطوات، تتوقف عند رد العميل</p>
        </div>
        <button onClick={() => setCreating(true)} className="flex items-center gap-1.5 bg-gold-primary text-gray-950 font-semibold text-sm px-4 py-2 rounded-lg font-cairo">
          <Plus size={16} /> تسلسل جديد
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" /></div>
      ) : sequences.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          <GitBranch size={40} className="mx-auto mb-3 text-gray-700" />
          <p className="font-cairo">لا توجد تسلسلات بعد</p>
          <p className="text-xs text-gray-600 mt-1">أنشئ تسلسلاً ثم سجّل العملاء فيه من صفحة العملاء</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {sequences.map((s) => (
            <div key={s.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
              <div className="flex items-start justify-between">
                <h3 className="font-semibold text-white font-cairo">{s.name}</h3>
                <span className={clsx('text-[10px] px-2 py-0.5 rounded-full border font-cairo', s.active ? 'text-green-400 bg-green-500/10 border-green-500/30' : 'text-gray-400 bg-gray-700 border-gray-600')}>{s.active ? 'نشط' : 'متوقف'}</span>
              </div>
              <div className="flex items-center gap-2 text-xs text-gray-400 font-cairo">
                <Clock size={12} /> {s.steps.length} خطوات
              </div>
              <div className="flex gap-2 text-[11px] font-cairo">
                <span className="text-blue-400">جارٍ {s.stats.active || 0}</span>
                <span className="text-green-400">ردّ {s.stats.replied || 0}</span>
                <span className="text-gray-500">اكتمل {s.stats.completed || 0}</span>
              </div>
              <div className="flex items-center gap-2 pt-3 border-t border-gray-800">
                <button onClick={() => setEditing(s)} className="text-xs text-gray-400 hover:text-gold-primary font-cairo">تعديل</button>
                <button onClick={() => del(s.id)} className="text-gray-500 hover:text-red-400 mr-auto"><Trash2 size={13} /></button>
              </div>
            </div>
          ))}
        </div>
      )}

      {(creating || editing) && <Builder initial={editing || undefined} templates={templates} onClose={() => { setCreating(false); setEditing(null) }} onSaved={mutate} />}
    </div>
  )
}
