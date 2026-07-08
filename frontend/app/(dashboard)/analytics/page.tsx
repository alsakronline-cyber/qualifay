'use client'

import useSWR from 'swr'
import { clsx } from 'clsx'
import { Users, Send, MessageSquare, CalendarCheck, Trophy, Mail, GitBranch } from 'lucide-react'
import { dashboardApi } from '@/lib/api'

interface Analytics {
  funnel: { total: number; new: number; approved: number; contacted: number; replied: number; booked: number; won: number }
  channels: { whatsapp: { conversations: number; replied: number; reply_rate: number }; email: { conversations: number; replied: number; reply_rate: number } }
  sequences: Record<string, number>
  reachability: { on_whatsapp: number; not_on_whatsapp: number; unchecked: number }
}

function KPI({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <div className="flex items-center gap-2 text-gray-400 text-xs font-cairo mb-1.5">{icon}{label}</div>
      <div className="text-2xl font-bold text-white">{value}</div>
      {sub && <div className="text-[11px] text-gray-500 font-cairo mt-0.5">{sub}</div>}
    </div>
  )
}

const FUNNEL = [
  { key: 'total', label: 'إجمالي العملاء', color: 'bg-gray-500' },
  { key: 'new', label: 'جديد / قيد التأهيل', color: 'bg-blue-500' },
  { key: 'contacted', label: 'تم التواصل', color: 'bg-cyan-500' },
  { key: 'replied', label: 'ردّوا', color: 'bg-yellow-500' },
  { key: 'booked', label: 'حجزوا اجتماعاً', color: 'bg-orange-500' },
  { key: 'won', label: 'صفقات مربوحة', color: 'bg-green-500' },
] as const

export default function AnalyticsPage() {
  const { data, isLoading } = useSWR<Analytics>('analytics', () => dashboardApi.analytics().then((r) => r.data), { refreshInterval: 30000 })

  if (isLoading || !data) {
    return <div className="flex justify-center py-20"><div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" /></div>
  }

  const f = data.funnel
  const max = Math.max(f.total, 1)
  const pct = (n: number) => Math.round((n / max) * 100)
  const rate = (n: number, d: number) => d ? Math.round((n / d) * 100) : 0

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white font-cairo">التحليلات</h1>
        <p className="text-gray-400 text-sm mt-1">Analytics — أداء التحويل عبر القنوات والمراحل</p>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KPI icon={<Users size={13} />} label="إجمالي العملاء" value={f.total} />
        <KPI icon={<Send size={13} />} label="تم التواصل" value={f.contacted} sub={`${rate(f.contacted, f.total)}% من الإجمالي`} />
        <KPI icon={<MessageSquare size={13} />} label="معدل الرد" value={`${rate(f.replied, f.contacted)}%`} sub={`${f.replied} ردّوا`} />
        <KPI icon={<Trophy size={13} />} label="صفقات مربوحة" value={f.won} sub={`${rate(f.won, f.contacted)}% تحويل`} />
      </div>

      {/* Funnel */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <h2 className="text-sm font-semibold text-white font-cairo mb-4">قمع التحويل</h2>
        <div className="space-y-2.5">
          {FUNNEL.map((s) => (
            <div key={s.key}>
              <div className="flex justify-between text-xs font-cairo mb-1">
                <span className="text-gray-300">{s.label}</span>
                <span className="text-gray-500">{f[s.key]}</span>
              </div>
              <div className="h-6 bg-gray-800 rounded-lg overflow-hidden">
                <div className={clsx('h-full rounded-lg transition-all', s.color)} style={{ width: `${Math.max(pct(f[s.key]), f[s.key] > 0 ? 4 : 0)}%` }} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Channels + Sequences */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {[
          { key: 'whatsapp' as const, label: 'واتساب', icon: <MessageSquare size={15} className="text-wa-green" /> },
          { key: 'email' as const, label: 'البريد', icon: <Mail size={15} className="text-purple-400" /> },
        ].map((c) => {
          const d = data.channels[c.key]
          return (
            <div key={c.key} className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <div className="flex items-center gap-2 mb-3">{c.icon}<h3 className="font-semibold text-white font-cairo">{c.label}</h3></div>
              <div className="text-3xl font-bold text-white">{d.reply_rate}%</div>
              <p className="text-xs text-gray-500 font-cairo mt-1">معدل الرد · {d.replied} من {d.conversations} محادثة</p>
            </div>
          )
        })}

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-3"><GitBranch size={15} className="text-gold-primary" /><h3 className="font-semibold text-white font-cairo">التسلسلات</h3></div>
          <div className="space-y-1.5 text-sm font-cairo">
            <div className="flex justify-between"><span className="text-blue-400">جارٍ</span><span className="text-white">{data.sequences.active || 0}</span></div>
            <div className="flex justify-between"><span className="text-green-400">ردّوا</span><span className="text-white">{data.sequences.replied || 0}</span></div>
            <div className="flex justify-between"><span className="text-gray-500">اكتمل</span><span className="text-white">{data.sequences.completed || 0}</span></div>
          </div>
        </div>
      </div>

      {/* Reachability */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <h2 className="text-sm font-semibold text-white font-cairo mb-3">إمكانية الوصول (واتساب)</h2>
        <div className="grid grid-cols-3 gap-3 text-center">
          <div><div className="text-xl font-bold text-wa-green">{data.reachability.on_whatsapp}</div><div className="text-[11px] text-gray-500 font-cairo">على واتساب</div></div>
          <div><div className="text-xl font-bold text-amber-400">{data.reachability.not_on_whatsapp}</div><div className="text-[11px] text-gray-500 font-cairo">ليس على واتساب</div></div>
          <div><div className="text-xl font-bold text-gray-400">{data.reachability.unchecked}</div><div className="text-[11px] text-gray-500 font-cairo">غير مفحوص</div></div>
        </div>
      </div>
    </div>
  )
}
