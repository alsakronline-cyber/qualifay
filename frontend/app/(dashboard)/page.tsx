'use client'

import { useCallback } from 'react'
import useSWR from 'swr'
import Link from 'next/link'
import { clsx } from 'clsx'
import { formatDistanceToNow } from 'date-fns'
import { ar } from 'date-fns/locale'
import {
  Users,
  MessageSquare,
  Megaphone,
  CheckCircle,
  TrendingUp,
  Zap,
  Search,
} from 'lucide-react'
import { dashboardApi } from '@/lib/api'
import type { DashboardStats, WaInstance } from '@/lib/types'
import WarmupIndicator from '@/components/WarmupIndicator'

function StatCard({
  label,
  labelEn,
  value,
  icon: Icon,
  color,
  action,
}: {
  label: string
  labelEn: string
  value: number | string
  icon: React.ComponentType<{ size?: number; className?: string }>
  color: string
  action?: React.ReactNode
}) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 flex flex-col gap-3">
      <div className="flex items-start justify-between">
        <div className={clsx('w-10 h-10 rounded-lg flex items-center justify-center', color)}>
          <Icon size={20} />
        </div>
        {action}
      </div>
      <div>
        <div className="text-3xl font-bold text-white">{value}</div>
        <div className="text-sm font-medium text-gray-300 font-cairo mt-0.5">{label}</div>
        <div className="text-xs text-gray-500">{labelEn}</div>
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const { data, isLoading, mutate } = useSWR<DashboardStats>(
    '/dashboard/stats',
    () => dashboardApi.stats().then((r) => r.data),
    { refreshInterval: 30000 }
  )

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  const stats = data || {
    total_leads: 0,
    pending_review: 0,
    wa_messages_today: 0,
    active_campaigns: 0,
    recent_leads: [],
    recent_messages: [],
    instances: [],
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white font-cairo">لوحة التحكم</h1>
        <p className="text-gray-400 text-sm mt-1">مرحباً — إليك ملخص اليوم</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="إجمالي العملاء"
          labelEn="Total Leads"
          value={stats.total_leads}
          icon={Users}
          color="bg-blue-500/10 text-blue-400"
        />
        <StatCard
          label="بانتظار المراجعة"
          labelEn="Pending Review"
          value={stats.pending_review}
          icon={CheckCircle}
          color="bg-gold-primary/10 text-gold-primary"
          action={
            stats.pending_review > 0 ? (
              <Link
                href="/leads?tab=review"
                className="text-xs bg-gold-primary/10 text-gold-primary border border-gold-primary/30 px-2 py-1 rounded-md hover:bg-gold-primary/20 transition-colors font-cairo"
              >
                مراجعة
              </Link>
            ) : undefined
          }
        />
        <StatCard
          label="رسائل واتساب اليوم"
          labelEn="WA Messages Today"
          value={stats.wa_messages_today}
          icon={MessageSquare}
          color="bg-wa-green/10 text-wa-green"
        />
        <StatCard
          label="حملات نشطة"
          labelEn="Active Campaigns"
          value={stats.active_campaigns}
          icon={Megaphone}
          color="bg-purple-500/10 text-purple-400"
        />
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-2 gap-3">
        <Link
          href="/scrape"
          className="flex items-center gap-3 bg-gray-900 border border-gray-800 hover:border-gold-primary/40 rounded-xl p-4 transition-all group"
        >
          <div className="w-10 h-10 rounded-lg bg-gold-primary/10 text-gold-primary flex items-center justify-center group-hover:bg-gold-primary/20 transition-colors">
            <Search size={18} />
          </div>
          <div>
            <div className="text-sm font-semibold text-white font-cairo">بدء جمع البيانات</div>
            <div className="text-xs text-gray-500">Start Scrape</div>
          </div>
        </Link>
        <Link
          href="/leads?tab=review"
          className="flex items-center gap-3 bg-gray-900 border border-gray-800 hover:border-gold-primary/40 rounded-xl p-4 transition-all group"
        >
          <div className="w-10 h-10 rounded-lg bg-green-500/10 text-green-400 flex items-center justify-center group-hover:bg-green-500/20 transition-colors">
            <CheckCircle size={18} />
          </div>
          <div>
            <div className="text-sm font-semibold text-white font-cairo">
              طابور المراجعة
              {stats.pending_review > 0 && (
                <span className="mr-1.5 text-xs bg-gold-primary text-gray-950 px-1.5 rounded-full font-bold">
                  {stats.pending_review}
                </span>
              )}
            </div>
            <div className="text-xs text-gray-500">Review Queue</div>
          </div>
        </Link>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* WA Warmup */}
        <div className="xl:col-span-1">
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-4">
              <TrendingUp size={16} className="text-gold-primary" />
              <h2 className="text-sm font-semibold text-white font-cairo">مؤشرات الإحماء</h2>
            </div>
            {stats.instances?.length === 0 ? (
              <p className="text-gray-500 text-sm text-center py-4 font-cairo">لا توجد نسخ واتساب</p>
            ) : (
              <div className="space-y-3">
                {stats.instances?.map((inst: WaInstance) => (
                  <WarmupIndicator key={inst.id} instance={inst} />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Recent Activity */}
        <div className="xl:col-span-2 grid grid-rows-2 gap-4">
          {/* Recent Leads */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Zap size={16} className="text-gold-primary" />
                <h2 className="text-sm font-semibold text-white font-cairo">آخر العملاء المحتملين</h2>
              </div>
              <Link href="/leads" className="text-xs text-gold-primary hover:text-gold-dark">
                عرض الكل
              </Link>
            </div>
            <div className="space-y-2">
              {(stats.recent_leads || []).slice(0, 5).map((lead) => (
                <div
                  key={lead.id}
                  className="flex items-center justify-between py-2 border-b border-gray-800 last:border-0"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-7 h-7 rounded-full bg-gray-800 flex items-center justify-center text-xs text-gray-400">
                      {lead.company?.charAt(0) || '?'}
                    </div>
                    <div>
                      <div className="text-sm text-white font-cairo">{lead.company || lead.name || 'غير محدد'}</div>
                      <div className="text-xs text-gray-500">{lead.industry} · {lead.city}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {lead.bant_score !== undefined && (
                      <span
                        className={clsx(
                          'text-xs px-1.5 py-0.5 rounded font-bold',
                          lead.bant_score >= 70
                            ? 'bg-green-500/10 text-green-400'
                            : lead.bant_score >= 50
                            ? 'bg-yellow-500/10 text-yellow-400'
                            : 'bg-red-500/10 text-red-400'
                        )}
                      >
                        {lead.bant_score}
                      </span>
                    )}
                    <span className="text-xs text-gray-600">
                      {formatDistanceToNow(new Date(lead.created_at), { locale: ar, addSuffix: true })}
                    </span>
                  </div>
                </div>
              ))}
              {(stats.recent_leads || []).length === 0 && (
                <p className="text-center text-gray-600 text-sm py-3 font-cairo">لا توجد بيانات بعد</p>
              )}
            </div>
          </div>

          {/* Recent Messages */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <MessageSquare size={16} className="text-wa-green" />
                <h2 className="text-sm font-semibold text-white font-cairo">آخر الرسائل</h2>
              </div>
              <Link href="/inbox" className="text-xs text-gold-primary hover:text-gold-dark">
                الصندوق
              </Link>
            </div>
            <div className="space-y-2">
              {(stats.recent_messages || []).slice(0, 5).map((msg) => (
                <div
                  key={msg.id}
                  className="flex items-start justify-between py-2 border-b border-gray-800 last:border-0"
                >
                  <div className="flex items-start gap-2 flex-1 min-w-0">
                    <div
                      className={clsx(
                        'w-1.5 h-1.5 rounded-full mt-1.5 shrink-0',
                        msg.direction === 'inbound' ? 'bg-wa-green' : 'bg-blue-400'
                      )}
                    />
                    <p className="text-sm text-gray-300 truncate">{msg.content}</p>
                  </div>
                  <span className="text-xs text-gray-600 mr-2 shrink-0">
                    {formatDistanceToNow(new Date(msg.created_at), { locale: ar, addSuffix: true })}
                  </span>
                </div>
              ))}
              {(stats.recent_messages || []).length === 0 && (
                <p className="text-center text-gray-600 text-sm py-3 font-cairo">لا توجد رسائل بعد</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
