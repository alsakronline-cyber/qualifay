'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { clsx } from 'clsx'
import { Megaphone, Pause, Play, Plus, Rocket, Trash2, X, Users } from 'lucide-react'
import toast from 'react-hot-toast'
import { campaignsApi, sequencesApi } from '@/lib/api'
import { STAGE_LABELS } from '@/lib/stages'

interface Stats { enrolled: number; active: number; paused: number; completed: number; stopped: number; replied: number; reply_rate: number }
interface Campaign {
  id: string; name: string; status: string; channel: string; sequence_id?: string | null
  audience_filter: Record<string, unknown>; auto_enroll: boolean; stats: Stats
}
interface Seq { id: string; name: string }

const STATUS = {
  draft: { label: 'مسودة', cls: 'text-gray-400 bg-gray-700 border-gray-600' },
  running: { label: 'نشطة', cls: 'text-green-400 bg-green-500/10 border-green-500/30' },
  paused: { label: 'موقوفة', cls: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30' },
  done: { label: 'مكتملة', cls: 'text-gray-400 bg-gray-500/10 border-gray-500/30' },
} as const

const SOURCES = ['', 'google_maps', 'linkedin', 'facebook_groups', 'apollo', 'directories', 'websites', 'tenders', 'manual']
const STAGE_OPTS = ['', 'new', 'approved', 'replied', 'qualifying', 'meeting', 'proposal', 'negotiation']

function CreateModal({ sequences, onClose, onDone }: { sequences: Seq[]; onClose: () => void; onDone: () => void }) {
  const [name, setName] = useState('')
  const [channel, setChannel] = useState('whatsapp')
  const [sequenceId, setSequenceId] = useState('')
  const [autoEnroll, setAutoEnroll] = useState(true)
  const [af, setAf] = useState<Record<string, string>>({ stage: '', source: '', city: '', industry: '', min_score: '' })
  const [loading, setLoading] = useState(false)
  const setF = (k: string, v: string) => setAf((p) => ({ ...p, [k]: v }))

  async function save() {
    if (!name.trim()) { toast.error('أدخل اسم الحملة'); return }
    if (!sequenceId) { toast.error('اختر تسلسل الرسائل'); return }
    const audience_filter: Record<string, unknown> = {}
    Object.entries(af).forEach(([k, v]) => { if (v !== '') audience_filter[k] = k === 'min_score' ? Number(v) : v })
    setLoading(true)
    try {
      await campaignsApi.create({ name: name.trim(), channel, sequence_id: sequenceId, audience_filter, auto_enroll: autoEnroll })
      toast.success('تم إنشاء الحملة كمسودة — اضغط "إطلاق" لبدء التواصل')
      onDone(); onClose()
    } catch (e: unknown) { const err = e as { response?: { data?: { detail?: string } } }; toast.error(err?.response?.data?.detail || 'فشل') }
    finally { setLoading(false) }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 w-full max-w-md space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-white font-cairo">حملة جديدة</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-white"><X size={18} /></button>
        </div>

        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="اسم الحملة"
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo" />

        <div>
          <div className="text-xs text-gray-400 font-cairo mb-1.5">القناة</div>
          <div className="flex gap-2">
            {[['whatsapp', 'واتساب'], ['email', 'بريد'], ['both', 'كلاهما']].map(([v, l]) => (
              <button key={v} onClick={() => setChannel(v)} type="button"
                className={clsx('flex-1 py-2 rounded-lg text-sm border font-cairo', channel === v ? 'bg-gold-primary/15 border-gold-primary/40 text-gold-primary' : 'border-gray-700 text-gray-400')}>{l}</button>
            ))}
          </div>
        </div>

        {/* Audience */}
        <div className="border border-gray-800 rounded-lg p-3 space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-bold text-gold-primary font-cairo"><Users size={13} /> الجمهور (فلتر العملاء)</div>
          <div className="grid grid-cols-2 gap-2">
            <select value={af.stage} onChange={(e) => setF('stage', e.target.value)} className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-white font-cairo">
              {STAGE_OPTS.map((s) => <option key={s} value={s}>{s === '' ? 'كل المراحل' : STAGE_LABELS[s] || s}</option>)}
            </select>
            <select value={af.source} onChange={(e) => setF('source', e.target.value)} className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-white font-cairo">
              {SOURCES.map((s) => <option key={s} value={s}>{s === '' ? 'كل المصادر' : s}</option>)}
            </select>
            <input value={af.city} onChange={(e) => setF('city', e.target.value)} placeholder="المدينة" className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-white font-cairo" />
            <input value={af.industry} onChange={(e) => setF('industry', e.target.value)} placeholder="المجال" className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-white font-cairo" />
            <input value={af.min_score} onChange={(e) => setF('min_score', e.target.value)} type="number" placeholder="أقل تقييم BANT" className="col-span-2 bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-white font-cairo" />
          </div>
          <p className="text-[11px] text-gray-500 font-cairo">اترك الحقول فارغة لاستهداف كل العملاء المتاحين (الحالة: نشط فقط).</p>
        </div>

        {/* Engine */}
        <div>
          <div className="text-xs text-gray-400 font-cairo mb-1.5">محرّك الرسائل (التسلسل)</div>
          <select value={sequenceId} onChange={(e) => setSequenceId(e.target.value)} className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-cairo">
            <option value="">— اختر تسلسلاً —</option>
            {sequences.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          {sequences.length === 0 && <p className="text-[11px] text-yellow-500/80 font-cairo mt-1">لا توجد تسلسلات بعد — أنشئ واحداً من صفحة التسلسلات أولاً.</p>}
        </div>

        <label className="flex items-center gap-2 text-sm text-gray-300 font-cairo">
          <input type="checkbox" checked={autoEnroll} onChange={(e) => setAutoEnroll(e.target.checked)} className="accent-gold-primary" />
          مزامنة تلقائية — أضف العملاء الجدد المطابقين للفلتر تلقائياً
        </label>

        <div className="flex gap-2 pt-1">
          <button onClick={onClose} className="flex-1 py-2.5 rounded-lg border border-gray-700 text-gray-400 text-sm font-cairo">إلغاء</button>
          <button onClick={save} disabled={loading} className="flex-1 py-2.5 rounded-lg bg-gold-primary text-gray-950 font-semibold text-sm disabled:opacity-50 font-cairo">{loading ? '...' : 'إنشاء'}</button>
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="text-center">
      <div className="text-lg font-bold text-white">{value}</div>
      <div className="text-[11px] text-gray-500 font-cairo">{label}</div>
    </div>
  )
}

export default function CampaignsPage() {
  const { data, mutate, isLoading } = useSWR('campaigns', () => campaignsApi.list().then((r) => r.data), { revalidateOnFocus: true })
  const { data: seqData } = useSWR('sequences-for-campaign', () => sequencesApi.list().then((r) => r.data))
  const campaigns: Campaign[] = data?.items || []
  const sequences: Seq[] = Array.isArray(seqData) ? seqData : (seqData?.items || [])
  const [creating, setCreating] = useState(false)

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); toast.success(ok); mutate() }
    catch (e: unknown) { const err = e as { response?: { data?: { detail?: string } } }; toast.error(err?.response?.data?.detail || 'فشل') }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white font-cairo flex items-center gap-2"><Megaphone size={22} /> الحملات</h1>
          <p className="text-gray-400 text-sm mt-1">اربط جمهوراً بتسلسل رسائل — والمزامنة تبقيه حياً</p>
        </div>
        <button onClick={() => setCreating(true)} className="flex items-center gap-1.5 bg-gold-primary text-gray-950 font-semibold text-sm px-4 py-2 rounded-lg font-cairo">
          <Plus size={16} /> حملة جديدة
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" /></div>
      ) : campaigns.length === 0 ? (
        <div className="text-center py-16 text-gray-500 font-cairo">لا توجد حملات بعد. أنشئ حملة تربط فلتر عملاء بتسلسل رسائل تلقائي.</div>
      ) : (
        <div className="space-y-3">
          {campaigns.map((c) => {
            const st = STATUS[c.status as keyof typeof STATUS] || STATUS.draft
            return (
              <div key={c.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-3">
                  <div className="flex-1 min-w-0">
                    <div className="text-white font-medium font-cairo truncate">{c.name}</div>
                    <div className="text-xs text-gray-500 font-cairo flex items-center gap-2 mt-0.5">
                      <span>{c.channel === 'whatsapp' ? 'واتساب' : c.channel === 'email' ? 'بريد' : 'واتساب + بريد'}</span>
                      {c.auto_enroll && <span className="text-gold-primary/70">• مزامنة تلقائية</span>}
                    </div>
                  </div>
                  <span className={clsx('text-[11px] px-2 py-0.5 rounded-full border font-cairo', st.cls)}>{st.label}</span>
                  {c.status === 'draft' && (
                    <button onClick={() => act(() => campaignsApi.launch(c.id), 'تم إطلاق الحملة')} className="flex items-center gap-1 text-xs text-gold-primary hover:text-gold-light font-cairo" title="إطلاق"><Rocket size={14} /> إطلاق</button>
                  )}
                  {c.status === 'running' && (
                    <button onClick={() => act(() => campaignsApi.pause(c.id), 'تم الإيقاف المؤقت')} className="text-gray-400 hover:text-yellow-400" title="إيقاف"><Pause size={15} /></button>
                  )}
                  {c.status === 'paused' && (
                    <button onClick={() => act(() => campaignsApi.resume(c.id), 'تم الاستئناف')} className="text-gray-400 hover:text-green-400" title="استئناف"><Play size={15} /></button>
                  )}
                  <button onClick={() => { if (confirm('حذف الحملة؟ سيتوقف تسلسل رسائلها.')) act(() => campaignsApi.remove(c.id), 'تم الحذف') }} className="text-gray-500 hover:text-red-400"><Trash2 size={15} /></button>
                </div>
                <div className="grid grid-cols-4 gap-2 pt-3 border-t border-gray-800">
                  <Stat label="مُسجَّل" value={c.stats.enrolled} />
                  <Stat label="نشط" value={c.stats.active} />
                  <Stat label="ردّ" value={c.stats.replied} />
                  <Stat label="معدل الرد" value={`${c.stats.reply_rate}%`} />
                </div>
              </div>
            )
          })}
        </div>
      )}

      {creating && <CreateModal sequences={sequences} onClose={() => setCreating(false)} onDone={mutate} />}
    </div>
  )
}
