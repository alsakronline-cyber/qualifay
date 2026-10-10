'use client'

// Site Factory — businesses without a website get a private multi-page preview site.
// Each one is scored (who's worth pursuing) and gets recommended services from the data that
// exists about it online; you assign it to yourself or a teammate. Nothing is sent until a
// human approves the intro, and the preview link only goes out after the business says
// "yes" (consent). See backend app/site_factory/state.py + insights.py.
import { Fragment, useState } from 'react'
import useSWR from 'swr'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'
import { format } from 'date-fns'
import {
  Globe, Search, Check, X, ExternalLink, Plus, CreditCard, Send, ShieldCheck, Loader2, ChevronDown, UserPlus, Flame,
} from 'lucide-react'
import { siteFactoryApi, teamApi } from '@/lib/api'
import SiteDesignPanel from '@/components/SiteDesignPanel'

interface Campaign {
  id: string; name: string; segment: string; areas: string[]; price_egp: number; service_prices?: Record<string, number>
  max_new_per_day: number; max_intros_per_day: number; instapay_handle?: string; active: boolean; last_discovery_at?: string
}
interface Service { id: string; title_ar: string; reason_ar: string; price_egp: number }
interface Prospect {
  id: string; business_name: string; segment: string; gap: string; phone?: string; city?: string; status: string
  approved: boolean; preview_url?: string; live_url?: string; last_inbound?: string; last_event_at?: string
  score?: number; tier: 'hot' | 'warm' | 'cold'; score_reasons: string[]; services: Service[]; package_egp: number
  assigned_to?: string | null
  profile: Record<string, unknown>
  design?: { style?: Record<string, unknown>; colors?: { primary?: string; accent?: string | null }; has_logo?: boolean }
}
interface Member { id: string; full_name?: string; email: string }

const STATUS: Record<string, { label: string; cls: string }> = {
  found: { label: 'بانتظار التصميم', cls: 'bg-gray-700 text-gray-300' },
  built: { label: 'المعاينة جاهزة', cls: 'bg-gray-700 text-gray-300' },
  awaiting_approval: { label: 'بانتظار موافقتك', cls: 'bg-amber-500/15 text-amber-300' },
  intro_sent: { label: 'تم إرسال التعريف', cls: 'bg-sky-500/15 text-sky-300' },
  opted_in: { label: 'وافق على المعاينة', cls: 'bg-sky-500/15 text-sky-300' },
  preview_sent: { label: 'استلم المعاينة', cls: 'bg-indigo-500/15 text-indigo-300' },
  changes_requested: { label: 'طلب تعديل', cls: 'bg-orange-500/15 text-orange-300' },
  payment_sent: { label: 'تم إرسال الدفع', cls: 'bg-violet-500/15 text-violet-300' },
  paid: { label: 'تم الدفع', cls: 'bg-green-500/15 text-green-300' },
  live: { label: 'منشور', cls: 'bg-green-500/20 text-green-300' },
  declined: { label: 'رفض', cls: 'bg-gray-800 text-gray-500' },
  cancelled: { label: 'ألغى', cls: 'bg-gray-800 text-gray-500' },
  expired: { label: 'انتهى بدون رد', cls: 'bg-gray-800 text-gray-500' },
  rejected: { label: 'استبعدته', cls: 'bg-gray-800 text-gray-500' },
  unreachable: { label: 'ليس على واتساب', cls: 'bg-gray-800 text-gray-500' },
}
const TIER = {
  hot: { label: 'ساخن', cls: 'bg-red-500/15 text-red-300 border-red-500/30' },
  warm: { label: 'دافئ', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/30' },
  cold: { label: 'بارد', cls: 'bg-gray-700/60 text-gray-400 border-gray-600' },
}
const SEGMENTS = [
  { v: 'manufacturer', l: 'مصانع' },
  { v: 'store', l: 'محلات' },
  { v: 'clinic', l: 'عيادات وأطباء' },
]
const SERVICE_LABELS: Record<string, string> = { website: 'موقع', gbp: 'جوجل', social: 'سوشيال', whatsapp: 'واتساب' }
const TABS = [
  { k: 'found', l: 'بانتظار التصميم' },
  { k: 'awaiting_approval', l: 'بانتظار الموافقة' },
  { k: 'intro_sent,opted_in,preview_sent,changes_requested,payment_sent', l: 'محادثات نشطة' },
  { k: 'paid,live', l: 'مبيعات' },
  { k: 'declined,cancelled,expired,rejected,unreachable', l: 'مغلقة' },
]
const OWNER_FILTERS = [
  { k: '', l: 'الكل' },
  { k: 'me', l: 'المسندة لي' },
  { k: 'none', l: 'غير مسندة' },
]
const FUNNEL = ['found', 'awaiting_approval', 'intro_sent', 'preview_sent', 'live']

function Badge({ s }: { s: string }) {
  const m = STATUS[s] || { label: s, cls: 'bg-gray-700 text-gray-300' }
  return <span className={clsx('text-xs px-2 py-0.5 rounded font-cairo whitespace-nowrap', m.cls)}>{m.label}</span>
}

export default function SiteFactoryPage() {
  const [tab, setTab] = useState(TABS[0].k)   // start on "waiting for design" 
  const [owner, setOwner] = useState('')
  const [hotOnly, setHotOnly] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [open, setOpen] = useState<string | null>(null)
  const [showNew, setShowNew] = useState(false)
  const [busy, setBusy] = useState(false)

  const { data: camps, mutate: mutCamps } = useSWR('sf-campaigns', () => siteFactoryApi.campaigns().then((r) => r.data))
  const { data: stats, mutate: mutStats } = useSWR('sf-stats', () => siteFactoryApi.stats().then((r) => r.data), { refreshInterval: 30000 })
  const { data: team } = useSWR('sf-team', () => teamApi.list().then((r) => r.data))
  const { data: rows, isLoading, mutate } = useSWR(['sf-prospects', tab, owner, hotOnly], () =>
    siteFactoryApi.prospects({ status: tab, assigned: owner || undefined, min_score: hotOnly ? 70 : undefined, sort: 'score', limit: 200 }).then((r) => r.data),
  { refreshInterval: 30000 })
  const campaigns: Campaign[] = Array.isArray(camps) ? camps : []
  const prospects: Prospect[] = Array.isArray(rows) ? rows : []
  const members: Member[] = Array.isArray(team) ? team : []
  const s: Record<string, number> = stats || {}
  const memberName = (id?: string | null) => members.find((m) => m.id === id)?.full_name || members.find((m) => m.id === id)?.email || ''

  const refresh = () => { mutate(); mutStats(); setSelected([]) }
  const toggle = (id: string) => setSelected((x) => (x.includes(id) ? x.filter((i) => i !== id) : [...x, id]))

  async function act(kind: 'approve' | 'reject') {
    if (!selected.length) return
    setBusy(true)
    try {
      const r = kind === 'approve' ? await siteFactoryApi.approve(selected) : await siteFactoryApi.reject(selected)
      toast.success(kind === 'approve' ? `تمت الموافقة على ${r.data.approved} — سيُرسل التعريف في ساعات العمل` : `تم استبعاد ${r.data.rejected} وحذف بياناتهم`)
      refresh()
    } catch { toast.error('تعذّر تنفيذ الإجراء') } finally { setBusy(false) }
  }

  async function assign(ids: string[], userId: string) {
    try {
      await siteFactoryApi.assign(ids, userId || null)
      toast.success(userId ? `تم الإسناد إلى ${memberName(userId)}` : 'تم إلغاء الإسناد')
      refresh()
    } catch { toast.error('تعذّر الإسناد') }
  }

  async function markPaid(p: Prospect) {
    const ref = window.prompt(`مرجع التحويل لـ ${p.business_name} (InstaPay / كاش):`)
    if (!ref) return
    try { await siteFactoryApi.markPaid(p.id, ref); toast.success('تم تسجيل الدفع ونشر الموقع'); refresh() }
    catch { toast.error('لا يمكن تسجيل الدفع في هذه المرحلة') }
  }

  async function resend(p: Prospect) {
    try { await siteFactoryApi.resendPreview(p.id); toast.success('تم إرسال المعاينة المعدّلة'); refresh() }
    catch { toast.error('تعذّر الإرسال') }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white font-cairo flex items-center gap-2"><Globe size={22} /> مصنع المواقع</h1>
          <p className="text-gray-400 text-sm mt-1 font-cairo">نجمع البيانات ← أنت تختار التصميم وتبني ← تراجع وتوافق ← تواصل بعد موافقة العميل ← بيع</p>
        </div>
        <button onClick={() => setShowNew((v) => !v)} className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gold-primary text-black font-semibold text-sm font-cairo">
          <Plus size={16} /> حملة جديدة
        </button>
      </div>

      <div className="flex items-start gap-3 rounded-xl border border-emerald-500/25 bg-emerald-500/5 p-4 text-sm text-emerald-200 font-cairo">
        <ShieldCheck size={18} className="mt-0.5 flex-none" />
        <p>لا تُرسل أي رسالة قبل موافقتك. الرسالة الأولى تطلب الإذن فقط، واللينك يُرسل بعد رد العميل بـ «نعم». متابعة واحدة فقط، وأي «إيقاف» أو «لا» يحذف بياناته نهائيًا.</p>
      </div>

      {showNew && <NewCampaign onDone={() => { setShowNew(false); mutCamps() }} />}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {FUNNEL.map((k) => (
          <div key={k} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <p className="text-2xl font-bold text-white">{(k === 'live' ? (s.live || 0) + (s.paid || 0) : s[k] || 0).toLocaleString()}</p>
            <p className="text-xs text-gray-400 font-cairo mt-1">{STATUS[k].label}</p>
          </div>
        ))}
      </div>

      {campaigns.length > 0 && (
        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3">
          {campaigns.map((c) => (
            <div key={c.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-2">
              <div className="flex justify-between items-center gap-2">
                <p className="text-white font-semibold font-cairo">{c.name}</p>
                <span className={clsx('text-xs px-2 py-0.5 rounded', c.active ? 'bg-green-500/15 text-green-300' : 'bg-gray-800 text-gray-500')}>{c.active ? 'نشطة' : 'متوقفة'}</span>
              </div>
              <p className="text-xs text-gray-400 font-cairo">{SEGMENTS.find((x) => x.v === c.segment)?.l} · {c.areas.join('، ')}</p>
              <p className="text-xs text-gray-500 font-cairo">حتى {c.max_new_per_day} نشاط جديد و{c.max_intros_per_day} تعريف يوميًا · آخر بحث: {c.last_discovery_at ? format(new Date(c.last_discovery_at), 'yyyy-MM-dd HH:mm') : '—'}</p>
              <button onClick={async () => { await siteFactoryApi.discoverNow(c.id); toast.success('بدأ البحث — النتائج تظهر خلال دقائق') }}
                className="inline-flex items-center gap-1 text-xs text-gold-primary font-cairo"><Search size={13} /> ابحث الآن</button>
            </div>
          ))}
        </div>
      )}

      {/* Tabs + filters + bulk actions */}
      <div className="space-y-3 border-b border-gray-800 pb-3">
        <div className="flex flex-wrap gap-2">
          {TABS.map((t) => (
            <button key={t.k} onClick={() => { setTab(t.k); setSelected([]) }}
              className={clsx('px-3 py-1.5 rounded-lg text-sm font-cairo', tab === t.k ? 'bg-gray-800 text-white' : 'text-gray-400 hover:text-white')}>
              {t.l}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {OWNER_FILTERS.map((f) => (
            <button key={f.k} onClick={() => setOwner(f.k)}
              className={clsx('px-2.5 py-1 rounded-md text-xs font-cairo border', owner === f.k ? 'border-gold-primary text-gold-primary' : 'border-gray-800 text-gray-400')}>{f.l}</button>
          ))}
          <button onClick={() => setHotOnly((v) => !v)}
            className={clsx('inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-cairo border', hotOnly ? 'border-red-500/50 text-red-300' : 'border-gray-800 text-gray-400')}>
            <Flame size={12} /> الساخنة فقط (70+)
          </button>
          {selected.length > 0 && (
            <div className="ms-auto flex flex-wrap items-center gap-2">
              <label className="inline-flex items-center gap-1 text-xs text-gray-300 font-cairo">
                <UserPlus size={14} />
                <select className="bg-gray-950 border border-gray-800 rounded-md px-2 py-1 text-xs" defaultValue=""
                  onChange={(e) => { if (e.target.value !== '__') assign(selected, e.target.value); e.target.value = '__' }}>
                  <option value="__" disabled>إسناد ({selected.length}) إلى…</option>
                  {members.map((m) => <option key={m.id} value={m.id}>{m.full_name || m.email}</option>)}
                  <option value="">— بدون إسناد —</option>
                </select>
              </label>
              {tab === 'awaiting_approval' && (
                <>
                  <button disabled={busy} onClick={() => act('approve')}
                    className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-green-600 disabled:opacity-40 text-white text-sm font-cairo"><Check size={14} /> موافقة ({selected.length})</button>
                  <button disabled={busy} onClick={() => act('reject')}
                    className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-gray-800 disabled:opacity-40 text-gray-200 text-sm font-cairo"><X size={14} /> استبعاد</button>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><Loader2 className="animate-spin text-gold-primary" /></div>
      ) : prospects.length === 0 ? (
        <p className="text-center text-gray-500 py-16 font-cairo">لا يوجد شيء هنا بعد</p>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-gray-400 text-xs font-cairo">
                <th className="px-3 py-3 w-8">
                  <input type="checkbox" aria-label="تحديد الكل" checked={selected.length === prospects.length}
                    onChange={(e) => setSelected(e.target.checked ? prospects.map((p) => p.id) : [])} />
                </th>
                <th className="text-right px-3 py-3">النشاط</th>
                <th className="text-right px-3 py-3">يستحق؟</th>
                <th className="text-right px-3 py-3">الخدمات المقترحة</th>
                <th className="text-right px-3 py-3">المسؤول</th>
                <th className="text-right px-3 py-3">الحالة</th>
                <th className="text-right px-3 py-3">إجراءات</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {prospects.map((p) => (
                <Fragment key={p.id}>
                  <tr className="hover:bg-gray-800/40 align-top">
                    <td className="px-3 py-3"><input type="checkbox" aria-label={`تحديد ${p.business_name}`} checked={selected.includes(p.id)} onChange={() => toggle(p.id)} /></td>
                    <td className="px-3 py-3">
                      <button onClick={() => setOpen(open === p.id ? null : p.id)} className="text-right">
                        <p className="text-gray-100 font-cairo inline-flex items-center gap-1">{p.business_name}<ChevronDown size={13} className={clsx('transition', open === p.id && 'rotate-180')} /></p>
                        <p className="text-xs text-gray-500">{SEGMENTS.find((x) => x.v === p.segment)?.l} · {p.city || '—'} · {p.gap === 'no_gbp' ? 'لا موقع ولا جوجل' : 'بدون موقع'}</p>
                      </button>
                    </td>
                    <td className="px-3 py-3">
                      <span className={clsx('inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded border font-cairo', TIER[p.tier]?.cls)}
                        title={(p.score_reasons || []).join('\n')}>
                        {p.score ?? '—'} · {TIER[p.tier]?.label}
                      </span>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex flex-wrap gap-1">
                        {(p.services || []).map((sv) => (
                          <span key={sv.id} title={`${sv.title_ar} — ${sv.reason_ar}`} className="text-[11px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-300 font-cairo">{SERVICE_LABELS[sv.id] || sv.id}</span>
                        ))}
                      </div>
                      {p.package_egp > 0 && <p className="text-[11px] text-gray-500 mt-1 font-cairo">الباقة: {p.package_egp.toLocaleString()} ج</p>}
                    </td>
                    <td className="px-3 py-3">
                      <select aria-label="المسؤول" className="bg-gray-950 border border-gray-800 rounded-md px-2 py-1 text-xs text-gray-200 max-w-[140px]"
                        value={p.assigned_to || ''} onChange={(e) => assign([p.id], e.target.value)}>
                        <option value="">—</option>
                        {members.map((m) => <option key={m.id} value={m.id}>{m.full_name || m.email}</option>)}
                      </select>
                    </td>
                    <td className="px-3 py-3"><Badge s={p.status} /></td>
                    <td className="px-3 py-3">
                      <div className="flex flex-wrap gap-2 text-xs font-cairo">
                        {(p.live_url || p.preview_url) && (
                          <a href={p.live_url || p.preview_url} target="_blank" rel="noopener" className="inline-flex items-center gap-1 text-gold-primary">
                            <ExternalLink size={13} /> {p.live_url ? 'الموقع' : 'المعاينة'}
                          </a>
                        )}
                        {p.status === 'changes_requested' && (
                          <button onClick={() => resend(p)} className="inline-flex items-center gap-1 text-sky-300"><Send size={13} /> أرسل المعدّلة</button>
                        )}
                        {p.status === 'payment_sent' && (
                          <button onClick={() => markPaid(p)} className="inline-flex items-center gap-1 text-green-300"><CreditCard size={13} /> سجّل الدفع</button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {open === p.id && (
                    <tr className="bg-gray-950/50">
                      <td />
                      <td colSpan={6} className="px-3 py-4">
                        {p.status === 'found' ? (
                          <SiteDesignPanel p={p} onBuilt={() => { setOpen(null); refresh() }} />
                        ) : (
                        <div className="grid md:grid-cols-3 gap-4 text-xs font-cairo">
                          <div>
                            <p className="text-gray-400 mb-2">لماذا هذا التقييم</p>
                            <ul className="space-y-1 text-gray-300 list-disc ps-4">{(p.score_reasons || []).map((r, i) => <li key={i}>{r}</li>)}</ul>
                          </div>
                          <div>
                            <p className="text-gray-400 mb-2">ماذا نبيع له ولماذا</p>
                            <ul className="space-y-2">
                              {(p.services || []).map((sv) => (
                                <li key={sv.id} className="text-gray-300"><span className="text-white">{sv.title_ar}</span> — {sv.price_egp.toLocaleString()} ج<br /><span className="text-gray-500">{sv.reason_ar}</span></li>
                              ))}
                            </ul>
                          </div>
                          <div className="space-y-1 text-gray-400">
                            <p>الهاتف: <span dir="ltr" className="text-gray-200">{p.phone || '—'}</span></p>
                            <p>آخر رد: <span className="text-gray-200">{p.last_inbound || '—'}</span></p>
                            <p>آخر نشاط: {p.last_event_at ? format(new Date(p.last_event_at), 'yyyy-MM-dd HH:mm') : '—'}</p>
                            {p.assigned_to && <p>المسؤول: <span className="text-gray-200">{memberName(p.assigned_to)}</span></p>}
                            {p.design?.style && <p>التصميم: <span className="text-gray-200">{String(p.design.style.title || p.design.style.url || '')}</span></p>}
                          </div>
                        </div>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function NewCampaign({ onDone }: { onDone: () => void }) {
  const [f, setF] = useState({ name: '', segment: 'manufacturer', areas: '', max_new_per_day: 25, max_intros_per_day: 15, instapay_handle: '' })
  const [prices, setPrices] = useState({ website: 4500, gbp: 1500, social: 2500, whatsapp: 2000 })
  const [saving, setSaving] = useState(false)
  const set = (k: string, v: string | number) => setF((x) => ({ ...x, [k]: v }))

  async function save() {
    if (!f.name.trim() || !f.areas.trim()) { toast.error('اكتب اسم الحملة والمناطق'); return }
    setSaving(true)
    try {
      await siteFactoryApi.createCampaign({
        ...f, price_egp: prices.website, service_prices: prices,
        areas: f.areas.split(/[,،\n]/).map((a) => a.trim()).filter(Boolean), instapay_handle: f.instapay_handle || null,
      })
      toast.success('تم إنشاء الحملة — أول بحث يومي 8:30 صباحًا، أو اضغط «ابحث الآن»')
      onDone()
    } catch { toast.error('تعذّر إنشاء الحملة') } finally { setSaving(false) }
  }

  const input = 'w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-100 font-cairo'
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 grid md:grid-cols-2 gap-4">
      <label className="space-y-1"><span className="text-xs text-gray-400 font-cairo">اسم الحملة</span>
        <input className={input} value={f.name} onChange={(e) => set('name', e.target.value)} placeholder="مصانع العاشر — دفعة 1" /></label>
      <label className="space-y-1"><span className="text-xs text-gray-400 font-cairo">الشريحة</span>
        <select className={input} value={f.segment} onChange={(e) => set('segment', e.target.value)}>
          {SEGMENTS.map((x) => <option key={x.v} value={x.v}>{x.l}</option>)}
        </select></label>
      <label className="space-y-1 md:col-span-2"><span className="text-xs text-gray-400 font-cairo">المناطق (افصل بفاصلة)</span>
        <input className={input} value={f.areas} onChange={(e) => set('areas', e.target.value)} placeholder="10th of Ramadan, 6th of October" /></label>
      <div className="md:col-span-2 grid grid-cols-2 md:grid-cols-4 gap-3">
        {(Object.keys(prices) as (keyof typeof prices)[]).map((k) => (
          <label key={k} className="space-y-1"><span className="text-xs text-gray-400 font-cairo">سعر {SERVICE_LABELS[k]} (ج)</span>
            <input type="number" className={input} value={prices[k]} onChange={(e) => setPrices((x) => ({ ...x, [k]: Number(e.target.value) }))} /></label>
        ))}
      </div>
      <label className="space-y-1"><span className="text-xs text-gray-400 font-cairo">InstaPay (اختياري)</span>
        <input className={input} value={f.instapay_handle} onChange={(e) => set('instapay_handle', e.target.value)} placeholder="name@instapay" dir="ltr" /></label>
      <div className="grid grid-cols-2 gap-3">
        <label className="space-y-1"><span className="text-xs text-gray-400 font-cairo">نشاطات جديدة/يوم</span>
          <input type="number" className={input} value={f.max_new_per_day} onChange={(e) => set('max_new_per_day', Number(e.target.value))} /></label>
        <label className="space-y-1"><span className="text-xs text-gray-400 font-cairo">رسائل تعريف/يوم</span>
          <input type="number" className={input} value={f.max_intros_per_day} onChange={(e) => set('max_intros_per_day', Number(e.target.value))} /></label>
      </div>
      <div className="md:col-span-2 flex justify-end">
        <button disabled={saving} onClick={save} className="px-4 py-2 rounded-lg bg-gold-primary text-black font-semibold text-sm font-cairo disabled:opacity-50">إنشاء الحملة</button>
      </div>
    </div>
  )
}
