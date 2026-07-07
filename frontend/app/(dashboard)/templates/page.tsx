'use client'

import { useState, useRef, useCallback } from 'react'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { Plus, FileText, Pencil, Trash2, X, Copy, MessageSquare, Mail } from 'lucide-react'
import { templatesApi } from '@/lib/api'
import { renderTemplate, TEMPLATE_VARS as VARS } from '@/lib/templates'

interface Template {
  id: string
  name: string
  channel: 'email' | 'whatsapp' | 'both'
  category?: string
  subject?: string
  body: string
}

const CHANNELS = [
  { key: 'both', label: 'كلاهما' },
  { key: 'whatsapp', label: 'واتساب' },
  { key: 'email', label: 'بريد' },
]

function ChannelBadge({ channel }: { channel: string }) {
  if (channel === 'email') return <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-purple-500/15 text-purple-400 border border-purple-500/25 font-cairo"><Mail size={10} /> بريد</span>
  if (channel === 'whatsapp') return <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-wa-green/15 text-wa-green border border-wa-green/25 font-cairo"><MessageSquare size={10} /> واتساب</span>
  return <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-gold-primary/15 text-gold-primary border border-gold-primary/25 font-cairo">كلاهما</span>
}

function Editor({ initial, onClose, onSaved }: { initial?: Template; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState<Template>(initial || { id: '', name: '', channel: 'both', category: '', subject: '', body: '' })
  const [saving, setSaving] = useState(false)
  const bodyRef = useRef<HTMLTextAreaElement>(null)
  const set = (k: keyof Template, v: string) => setF((p) => ({ ...p, [k]: v }))

  const insertVar = (v: string) => {
    const ta = bodyRef.current
    if (!ta) { set('body', (f.body || '') + v); return }
    const s = ta.selectionStart, e = ta.selectionEnd
    const next = (f.body || '').slice(0, s) + v + (f.body || '').slice(e)
    set('body', next)
    requestAnimationFrame(() => { ta.focus(); ta.selectionStart = ta.selectionEnd = s + v.length })
  }

  async function save() {
    if (!f.name.trim() || !f.body.trim()) { toast.error('أدخل اسم القالب والنص'); return }
    setSaving(true)
    const payload = { name: f.name, channel: f.channel, category: f.category || undefined, subject: f.subject || undefined, body: f.body }
    try {
      if (f.id) await templatesApi.update(f.id, payload)
      else await templatesApi.create(payload)
      toast.success('تم الحفظ')
      onSaved(); onClose()
    } catch { toast.error('فشل الحفظ') }
    finally { setSaving(false) }
  }

  const showSubject = f.channel !== 'whatsapp'

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl w-full max-w-3xl max-h-[92vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
          <h3 className="font-semibold text-white font-cairo">{f.id ? 'تعديل القالب' : 'قالب جديد'}</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-white"><X size={18} /></button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-0 flex-1 overflow-hidden">
          {/* Editor */}
          <div className="p-6 space-y-4 overflow-y-auto border-l border-gray-800">
            <div>
              <label className="block text-xs text-gray-400 font-cairo mb-1.5">اسم القالب</label>
              <input value={f.name} onChange={(e) => set('name', e.target.value)} dir="rtl"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 font-cairo mb-1.5">القناة</label>
              <div className="flex gap-1 bg-gray-800 border border-gray-700 rounded-lg p-0.5">
                {CHANNELS.map((c) => (
                  <button key={c.key} onClick={() => set('channel', c.key)}
                    className={clsx('flex-1 text-xs py-1.5 rounded-md font-cairo transition-colors',
                      f.channel === c.key ? 'bg-gold-primary text-gray-950 font-semibold' : 'text-gray-400 hover:text-white')}>
                    {c.label}
                  </button>
                ))}
              </div>
            </div>
            {showSubject && (
              <div>
                <label className="block text-xs text-gray-400 font-cairo mb-1.5">عنوان البريد (Subject)</label>
                <input value={f.subject || ''} onChange={(e) => set('subject', e.target.value)} dir="rtl"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo" />
              </div>
            )}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs text-gray-400 font-cairo">النص</label>
                <div className="flex flex-wrap gap-1">
                  {VARS.map((v) => (
                    <button key={v.key} onClick={() => insertVar(v.key)} title={`إدراج ${v.label}`}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 border border-gray-700 text-gold-primary hover:bg-gray-700 font-mono">
                      {v.label}
                    </button>
                  ))}
                </div>
              </div>
              <textarea ref={bodyRef} value={f.body} onChange={(e) => set('body', e.target.value)} rows={8} dir="rtl"
                placeholder="اكتب نص الرسالة... استخدم المتغيرات أعلاه"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo resize-none leading-relaxed" />
              <p className="text-[10px] text-gray-600 mt-1 font-cairo">تُستبدل المتغيرات ببيانات العميل عند الإرسال.</p>
            </div>
          </div>

          {/* Live preview */}
          <div className="p-6 bg-gray-950/40 overflow-y-auto">
            <p className="text-xs text-gray-500 font-cairo mb-3">معاينة مباشرة (ببيانات تجريبية)</p>
            <div className="bg-gray-800 rounded-2xl p-4 shadow-inner">
              {showSubject && f.subject && (
                <p className="text-sm font-semibold text-white font-cairo mb-2 pb-2 border-b border-gray-700">{renderTemplate(f.subject)}</p>
              )}
              <p className="text-sm text-gray-100 font-cairo whitespace-pre-wrap leading-relaxed">
                {renderTemplate(f.body) || <span className="text-gray-600">ستظهر المعاينة هنا…</span>}
              </p>
            </div>
          </div>
        </div>

        <div className="flex gap-2 px-6 py-4 border-t border-gray-800">
          <button onClick={onClose} className="px-4 py-2 rounded-lg border border-gray-700 text-gray-400 hover:text-white text-sm font-cairo">إلغاء</button>
          <button onClick={save} disabled={saving} className="flex-1 py-2 rounded-lg bg-gold-primary text-gray-950 font-semibold text-sm disabled:opacity-50 font-cairo">
            {saving ? 'جارٍ الحفظ...' : 'حفظ القالب'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function TemplatesPage() {
  const { data, mutate, isLoading } = useSWR('templates', () => templatesApi.list().then((r) => r.data))
  const templates: Template[] = Array.isArray(data) ? data : []
  const [editing, setEditing] = useState<Template | null>(null)
  const [creating, setCreating] = useState(false)

  const del = useCallback(async (id: string) => {
    if (!confirm('حذف هذا القالب؟')) return
    try { await templatesApi.remove(id); toast.success('تم الحذف'); mutate() }
    catch { toast.error('فشل الحذف') }
  }, [mutate])

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white font-cairo">القوالب</h1>
          <p className="text-gray-400 text-sm mt-1">Templates — رسائل جاهزة للواتساب والبريد، سهلة التعديل</p>
        </div>
        <button onClick={() => setCreating(true)} className="flex items-center gap-1.5 bg-gold-primary text-gray-950 font-semibold text-sm px-4 py-2 rounded-lg font-cairo">
          <Plus size={16} /> قالب جديد
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" /></div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {templates.map((t) => (
            <div key={t.id} className="group bg-gray-900 border border-gray-800 rounded-xl p-4 flex flex-col hover:border-gray-700 transition-colors">
              <div className="flex items-start justify-between gap-2 mb-2">
                <h3 className="font-semibold text-white font-cairo truncate">{t.name}</h3>
                <ChannelBadge channel={t.channel} />
              </div>
              {t.subject && <p className="text-xs text-gray-400 font-cairo mb-1 truncate">📧 {renderTemplate(t.subject)}</p>}
              <p className="text-xs text-gray-500 font-cairo line-clamp-3 whitespace-pre-wrap flex-1 leading-relaxed">{renderTemplate(t.body)}</p>
              <div className="flex items-center gap-2 mt-3 pt-3 border-t border-gray-800">
                <button onClick={() => { navigator.clipboard.writeText(renderTemplate(t.body)); toast.success('تم النسخ') }}
                  className="flex items-center gap-1 text-xs text-gray-400 hover:text-white font-cairo"><Copy size={12} /> نسخ</button>
                <button onClick={() => setEditing(t)} className="flex items-center gap-1 text-xs text-gray-400 hover:text-gold-primary font-cairo mr-auto"><Pencil size={12} /> تعديل</button>
                <button onClick={() => del(t.id)} className="text-gray-500 hover:text-red-400"><Trash2 size={13} /></button>
              </div>
            </div>
          ))}
          {templates.length === 0 && (
            <div className="col-span-full text-center py-16 text-gray-500">
              <FileText size={40} className="mx-auto mb-3 text-gray-700" />
              <p className="font-cairo">لا توجد قوالب بعد</p>
            </div>
          )}
        </div>
      )}

      {(creating || editing) && (
        <Editor initial={editing || undefined} onClose={() => { setCreating(false); setEditing(null) }} onSaved={mutate} />
      )}
    </div>
  )
}
