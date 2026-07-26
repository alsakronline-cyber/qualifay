'use client'

import { useState, useEffect } from 'react'
import useSWR from 'swr'
import Link from 'next/link'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { Rocket, MapPin, Search, Building2, FileText, Users, Briefcase, Facebook, Sparkles, Megaphone, Clock, Zap, CheckCheck, Send, MessageSquareReply, Trophy, Play } from 'lucide-react'
import { scrapeApi } from '@/lib/api'

interface SourceRow { source: string; enabled: boolean; monthly_cap: number; monthly_count: number; hour_cairo: number; last_run_at: string | null }
interface Growth {
  plan: string; monthly_lead_limit: number; autonomy: string
  profile: { industry: string; cities: string }
  sources: SourceRow[]
  funnel: { leads_total: number; pending_review: number; approved: number; replied: number; won: number }
}

const SOURCE_META: Record<string, { label: string; icon: React.ComponentType<{ size?: number; className?: string }> }> = {
  google_maps: { label: 'خرائط جوجل', icon: MapPin },
  web_scrape: { label: 'مواقع الشركات', icon: Search },
  directories: { label: 'الأدلة', icon: Building2 },
  tender: { label: 'المناقصات', icon: FileText },
  apollo: { label: 'Apollo', icon: Users },
  linkedin: { label: 'LinkedIn', icon: Briefcase },
  facebook: { label: 'مجموعات فيسبوك', icon: Facebook },
  enrichment: { label: 'الإثراء', icon: Sparkles },
  competitor_ads: { label: 'إعلانات المنافسين', icon: Megaphone },
}

const AUTONOMY_LABEL: Record<string, string> = { full: 'وكيل كامل', copilot: 'مساعد ذكي', manual: 'يدوي', off: 'متوقّف' }

function Stat({ label, value, icon: Icon, color }: { label: string; value: number; icon: React.ComponentType<{ size?: number; className?: string }>; color: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-3 text-center">
      <Icon size={16} className={clsx('mx-auto mb-1', color)} />
      <div className="text-xl font-bold text-white">{value}</div>
      <div className="text-[11px] text-gray-400 font-cairo">{label}</div>
    </div>
  )
}

export default function GrowthPage() {
  const { data, mutate, isLoading } = useSWR('growth', () => scrapeApi.getGrowth().then((r) => r.data as Growth))
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [hour, setHour] = useState(9)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (data) {
      setSelected(new Set(data.sources.filter((s) => s.enabled).map((s) => s.source)))
      const on = data.sources.find((s) => s.enabled)
      if (on) setHour(on.hour_cairo)
    }
  }, [data])

  if (isLoading || !data) return <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" /></div>

  const toggle = (src: string) => setSelected((s) => { const n = new Set(s); n.has(src) ? n.delete(src) : n.add(src); return n })
  const perSource = selected.size ? Math.max(Math.floor(data.monthly_lead_limit / selected.size), 30) : 0
  const perDay = selected.size ? Math.max(Math.floor(perSource / 26), 5) : 0

  async function activate() {
    if (selected.size === 0) return toast.error('اختر مصدراً واحداً على الأقل')
    setSaving(true)
    try { await scrapeApi.setupGrowth({ sources: Array.from(selected), hour_cairo: hour }); toast.success('تم تفعيل خطة النمو التلقائي'); await mutate() }
    catch (e: unknown) { toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'فشل') }
    finally { setSaving(false) }
  }

  const noProfile = !data.profile.industry && !data.profile.cities

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center gap-2">
        <Rocket size={22} className="text-gold-primary" />
        <div>
          <h1 className="text-2xl font-bold text-white font-cairo">النمو التلقائي</h1>
          <p className="text-gray-400 text-sm font-cairo">اختر مصادرك، والنظام يجمع ويؤهّل ويبدأ التواصل تلقائياً حسب وضع التشغيل.</p>
        </div>
      </div>

      {/* Context: profile + plan + autonomy */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-3">
          <div className="text-xs text-gray-500 font-cairo mb-0.5">المجال / المدن</div>
          <div className="text-sm text-white font-cairo truncate">{data.profile.industry || '—'} {data.profile.cities ? `· ${data.profile.cities}` : ''}</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-3">
          <div className="text-xs text-gray-500 font-cairo mb-0.5">حد الخطة الشهري</div>
          <div className="text-sm text-white font-cairo">{data.monthly_lead_limit.toLocaleString()} عميل · خطة {data.plan}</div>
        </div>
        <Link href="/activity" className="bg-gray-900 border border-gray-800 hover:border-gold-primary/40 rounded-xl p-3 transition-colors">
          <div className="text-xs text-gray-500 font-cairo mb-0.5">وضع التشغيل</div>
          <div className="text-sm text-gold-primary font-cairo">{AUTONOMY_LABEL[data.autonomy] || data.autonomy} ←</div>
        </Link>
      </div>

      {noProfile && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-3 text-sm text-yellow-300 font-cairo">
          لم يكتمل ملفك بعد. <Link href="/onboarding" className="underline">أكمل الإعداد مع المساعد الذكي</Link> ليستهدف النظام المجال والمدن الصحيحة.
        </div>
      )}

      {/* Sources */}
      <div>
        <h2 className="text-sm font-bold text-white font-cairo mb-2">مصادر الجمع (اختر ما تريد تفعيله)</h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {data.sources.map((s) => {
            const meta = SOURCE_META[s.source] || { label: s.source, icon: Search }
            const Icon = meta.icon
            const on = selected.has(s.source)
            return (
              <button key={s.source} onClick={() => toggle(s.source)}
                className={clsx('rounded-xl border p-3 text-right transition-colors', on ? 'border-gold-primary bg-gold-primary/10' : 'border-gray-800 bg-gray-900 hover:border-gray-700')}>
                <div className="flex items-center justify-between">
                  <Icon size={16} className={on ? 'text-gold-primary' : 'text-gray-400'} />
                  <span className={clsx('w-8 h-4.5 rounded-full relative transition-colors', on ? 'bg-gold-primary' : 'bg-gray-700')} style={{ height: 18, width: 32 }}>
                    <span className={clsx('absolute top-0.5 w-3.5 h-3.5 bg-white rounded-full transition-all', on ? 'left-0.5' : 'right-0.5')} />
                  </span>
                </div>
                <div className="text-sm text-white font-cairo mt-1.5">{meta.label}</div>
                {s.enabled && <div className="text-[10px] text-gray-500 font-cairo">{s.monthly_count}/{s.monthly_cap} هذا الشهر</div>}
              </button>
            )
          })}
        </div>
      </div>

      {/* Derived quantity + time + activate */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2 text-sm text-gray-300 font-cairo">
          <Zap size={15} className="text-gold-primary" />
          {selected.size ? <>~<b className="text-white">{perDay}</b> عميل/يوم لكل مصدر · <b className="text-white">{(perSource * selected.size).toLocaleString()}</b>/شهر إجمالاً</> : 'اختر مصادر لرؤية الكمية'}
        </div>
        <div className="flex items-center gap-2 mr-auto">
          <Clock size={15} className="text-gray-400" />
          <select value={hour} onChange={(e) => setHour(parseInt(e.target.value))}
            className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-sm text-white font-cairo focus:outline-none focus:ring-1 focus:ring-gold-primary">
            {Array.from({ length: 24 }, (_, i) => <option key={i} value={i}>{i}:00</option>)}
          </select>
          <span className="text-xs text-gray-500 font-cairo">بتوقيت القاهرة</span>
        </div>
        <button onClick={activate} disabled={saving} className="flex items-center gap-1.5 bg-gold-primary text-gray-950 font-semibold text-sm px-4 py-2 rounded-lg disabled:opacity-50 font-cairo">
          <Play size={15} /> {saving ? 'جارٍ...' : 'تفعيل الخطة'}
        </button>
      </div>

      {/* Funnel */}
      <div>
        <h2 className="text-sm font-bold text-white font-cairo mb-2">مسار النمو</h2>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
          <Stat label="مجموع العملاء" value={data.funnel.leads_total} icon={Users} color="text-blue-400" />
          <Stat label="بانتظار المراجعة" value={data.funnel.pending_review} icon={CheckCheck} color="text-gold-primary" />
          <Stat label="معتمد/تواصل" value={data.funnel.approved} icon={Send} color="text-cyan-400" />
          <Stat label="رد" value={data.funnel.replied} icon={MessageSquareReply} color="text-wa-green" />
          <Stat label="صفقات مربوحة" value={data.funnel.won} icon={Trophy} color="text-green-400" />
        </div>
      </div>
    </div>
  )
}
