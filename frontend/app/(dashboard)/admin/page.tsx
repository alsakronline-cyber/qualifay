'use client'

import useSWR from 'swr'
import Link from 'next/link'
import { clsx } from 'clsx'
import { ShieldCheck, Building2, UsersRound, Users, Send, MessageSquare, Hourglass, AlertTriangle, MailWarning, Ban } from 'lucide-react'
import { adminApi } from '@/lib/api'

type Icon = React.ComponentType<{ size?: number; className?: string }>

function Tile({ label, value, icon: Icon, color, href }: { label: string; value: number | string; icon: Icon; color: string; href?: string }) {
  const inner = (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex items-center gap-3 hover:border-gray-700 transition-colors h-full">
      <div className={clsx('w-10 h-10 rounded-lg flex items-center justify-center shrink-0', color)}><Icon size={18} /></div>
      <div className="min-w-0">
        <div className="text-2xl font-bold text-white leading-none">{value}</div>
        <div className="text-xs text-gray-400 font-cairo mt-1 truncate">{label}</div>
      </div>
    </div>
  )
  return href ? <Link href={href}>{inner}</Link> : inner
}

export default function AdminOverviewPage() {
  const { data } = useSWR('admin-overview', () => adminApi.overview().then((r) => r.data), { refreshInterval: 60000 })
  const s = data || {}

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center gap-2">
        <ShieldCheck size={22} className="text-gold-primary" />
        <div>
          <h1 className="text-2xl font-bold text-white font-cairo">لوحة المالك</h1>
          <p className="text-gray-400 text-sm font-cairo">إدارة المنصة بالكامل — كل الشركات والحسابات.</p>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Tile label="الشركات" value={s.tenants ?? 0} icon={Building2} color="bg-blue-500/10 text-blue-400" href="/admin/companies" />
        <Tile label="الحسابات" value={s.users ?? 0} icon={UsersRound} color="bg-purple-500/10 text-purple-400" href="/admin/accounts" />
        <Tile label="إجمالي العملاء" value={s.leads ?? 0} icon={Users} color="bg-gold-primary/10 text-gold-primary" />
        <Tile label="رسائل ٢٤ساعة" value={s.messages_24h ?? 0} icon={MessageSquare} color="bg-wa-green/10 text-wa-green" />
        <Tile label="مُرسل ٢٤ساعة" value={s.sent_24h ?? 0} icon={Send} color="bg-cyan-500/10 text-cyan-400" />
        <Tile label="تجارب نشطة" value={s.active_trials ?? 0} icon={Hourglass} color="bg-green-500/10 text-green-400" />
        <Tile label="تجارب تنتهي ٧أيام" value={s.trials_expiring_7d ?? 0} icon={AlertTriangle} color="bg-yellow-500/10 text-yellow-400" href="/admin/companies" />
        <Tile label="بريد غير مُفعّل" value={s.unverified_users ?? 0} icon={MailWarning} color="bg-orange-500/10 text-orange-400" href="/admin/accounts" />
      </div>

      {(s.suspended_tenants ?? 0) > 0 && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 flex items-center gap-2">
          <Ban size={16} className="text-red-400" />
          <span className="text-sm text-red-300 font-cairo">{s.suspended_tenants} شركة موقوفة حالياً.</span>
          <Link href="/admin/companies" className="text-sm text-gold-primary mr-auto font-cairo">إدارة</Link>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Link href="/admin/companies" className="bg-gray-900 border border-gray-800 hover:border-gold-primary/40 rounded-xl p-4 flex items-center gap-3 transition-colors">
          <Building2 size={20} className="text-gold-primary" />
          <div><div className="text-sm font-semibold text-white font-cairo">الشركات</div><div className="text-xs text-gray-500 font-cairo">الخطط، التجارب، الإيقاف والتفعيل</div></div>
        </Link>
        <Link href="/admin/accounts" className="bg-gray-900 border border-gray-800 hover:border-gold-primary/40 rounded-xl p-4 flex items-center gap-3 transition-colors">
          <UsersRound size={20} className="text-gold-primary" />
          <div><div className="text-sm font-semibold text-white font-cairo">الحسابات</div><div className="text-xs text-gray-500 font-cairo">التفعيل، الصلاحيات، كلمات المرور، الحذف</div></div>
        </Link>
      </div>
    </div>
  )
}
