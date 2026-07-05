'use client'

import useSWR from 'swr'
import { clsx } from 'clsx'
import { formatDistanceToNow } from 'date-fns'
import { ar } from 'date-fns/locale'
import { Megaphone, Pause, Play } from 'lucide-react'
import toast from 'react-hot-toast'
import { campaignsApi } from '@/lib/api'
import type { Campaign } from '@/lib/types'

const STATUS_CONFIG = {
  draft: { label: 'مسودة', color: 'text-gray-400', bg: 'bg-gray-700' },
  running: { label: 'نشطة', color: 'text-green-400', bg: 'bg-green-500/10' },
  paused: { label: 'موقوفة', color: 'text-yellow-400', bg: 'bg-yellow-500/10' },
  completed: { label: 'مكتملة', color: 'text-blue-400', bg: 'bg-blue-500/10' },
  failed: { label: 'فشلت', color: 'text-red-400', bg: 'bg-red-500/10' },
}

export default function CampaignsPage() {
  const { data, mutate, isLoading } = useSWR(
    'campaigns',
    () => campaignsApi.list().then((r) => r.data),
    { revalidateOnFocus: true }
  )
  const campaigns: Campaign[] = data?.items || data || []

  async function handleToggle(c: Campaign) {
    try {
      if (c.status === 'running') {
        await campaignsApi.pause(c.id)
        toast.success('تم إيقاف الحملة مؤقتاً')
      } else {
        await campaignsApi.resume(c.id)
        toast.success('تم استئناف الحملة')
      }
      mutate()
    } catch { toast.error('فشل تحديث الحملة') }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white font-cairo">الحملات</h1>
        <p className="text-gray-400 text-sm mt-1">Campaigns</p>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16">
          <div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" />
        </div>
      ) : campaigns.length === 0 ? (
        <div className="text-center py-20 text-gray-600">
          <Megaphone size={48} className="mx-auto mb-3 text-gray-700" />
          <p className="font-cairo">لا توجد حملات بعد</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {campaigns.map((c) => {
            const cfg = STATUS_CONFIG[c.status] || STATUS_CONFIG.draft
            return (
              <div key={c.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
                <div className="flex items-start justify-between">
                  <h3 className="font-semibold text-white font-cairo">{c.name}</h3>
                  <span className={clsx('text-xs px-2 py-0.5 rounded font-semibold font-cairo', cfg.bg, cfg.color)}>
                    {cfg.label}
                  </span>
                </div>
                <div className="flex gap-4 text-sm">
                  <div>
                    <div className="text-white font-bold">{c.sent_count}</div>
                    <div className="text-xs text-gray-500 font-cairo">مُرسل</div>
                  </div>
                  <div>
                    <div className="text-white font-bold">{c.replied_count}</div>
                    <div className="text-xs text-gray-500 font-cairo">رد</div>
                  </div>
                  {c.sent_count > 0 && (
                    <div>
                      <div className="text-white font-bold">{Math.round((c.replied_count / c.sent_count) * 100)}%</div>
                      <div className="text-xs text-gray-500">Reply Rate</div>
                    </div>
                  )}
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-600">
                    {formatDistanceToNow(new Date(c.created_at), { locale: ar, addSuffix: true })}
                  </span>
                  {(c.status === 'running' || c.status === 'paused') && (
                    <button
                      onClick={() => handleToggle(c)}
                      className={clsx(
                        'flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border font-semibold transition-colors font-cairo',
                        c.status === 'running'
                          ? 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30'
                          : 'bg-green-500/10 text-green-400 border-green-500/30'
                      )}
                    >
                      {c.status === 'running' ? <><Pause size={12} /> إيقاف</> : <><Play size={12} /> استئناف</>}
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
