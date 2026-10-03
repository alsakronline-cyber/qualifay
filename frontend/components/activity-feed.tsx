'use client'

import { useEffect, useState, useCallback } from 'react'
import { clsx } from 'clsx'
import { formatDistanceToNow } from 'date-fns'
import { ar } from 'date-fns/locale'
import {
  MessageSquare,
  CheckCircle,
  XCircle,
  Sparkles,
  Search,
  Wifi,
  Edit,
  Calendar,
  Activity,
} from 'lucide-react'
import { activityApi } from '@/lib/api'

interface ActivityEntry {
  id: string
  activity_type: string
  summary: string
  created_at: string
  user_name?: string
  metadata?: Record<string, unknown>
}

interface ActivityFeedProps {
  entityId: string
  entityType: 'lead' | 'conversation'
  className?: string
}

type IconConfig = {
  icon: React.ComponentType<{ size?: number; className?: string }>
  color: string
  bg: string
}

const ACTIVITY_ICONS: Record<string, IconConfig> = {
  message_sent:         { icon: MessageSquare, color: 'text-gray-400',   bg: 'bg-gray-500/10' },
  message_received:     { icon: MessageSquare, color: 'text-gray-400',   bg: 'bg-gray-500/10' },
  lead_approved:        { icon: CheckCircle,   color: 'text-green-400',  bg: 'bg-green-500/10' },
  lead_rejected:        { icon: XCircle,       color: 'text-red-400',    bg: 'bg-red-500/10' },
  ai_suggested:         { icon: Sparkles,      color: 'text-gray-400', bg: 'bg-gray-500/10' },
  ai_sent:              { icon: Sparkles,      color: 'text-gray-400', bg: 'bg-gray-500/10' },
  scrape_started:       { icon: Search,        color: 'text-gray-400', bg: 'bg-gray-500/10' },
  scrape_completed:     { icon: Search,        color: 'text-gray-400', bg: 'bg-gray-500/10' },
  instance_connected:   { icon: Wifi,          color: 'text-green-400',  bg: 'bg-green-500/10' },
  lead_updated:         { icon: Edit,          color: 'text-yellow-400', bg: 'bg-yellow-500/10' },
  appointment_booked:   { icon: Calendar,      color: 'text-gray-400',   bg: 'bg-gray-500/10' },
}

const DEFAULT_ICON: IconConfig = {
  icon: Activity,
  color: 'text-gray-400',
  bg: 'bg-gray-700',
}

function getIconConfig(type: string): IconConfig {
  // Try exact match first, then prefix match
  if (ACTIVITY_ICONS[type]) return ACTIVITY_ICONS[type]
  const prefix = Object.keys(ACTIVITY_ICONS).find((k) => type.startsWith(k.split('_')[0]))
  return prefix ? ACTIVITY_ICONS[prefix] : DEFAULT_ICON
}

export default function ActivityFeed({ entityId, entityType, className }: ActivityFeedProps) {
  const [entries, setEntries] = useState<ActivityEntry[]>([])
  const [loading, setLoading] = useState(true)

  const fetchActivity = useCallback(async () => {
    try {
      const res = await activityApi.list({
        entity_id: entityId,
        entity_type: entityType,
        limit: 20,
      })
      const items: ActivityEntry[] = Array.isArray(res.data) ? res.data : []
      setEntries(items)
    } catch {
      // silent fail — activity feed is secondary UI
    } finally {
      setLoading(false)
    }
  }, [entityId, entityType])

  useEffect(() => {
    fetchActivity()
    const interval = setInterval(fetchActivity, 30000)
    return () => clearInterval(interval)
  }, [fetchActivity])

  return (
    <div className={clsx('space-y-1', className)}>
      <h3 className="text-sm font-semibold text-white font-cairo mb-3 flex items-center gap-2">
        <Activity size={14} className="text-gray-400" />
        سجل النشاط
        <span className="text-xs text-gray-500 font-normal">Activity Log</span>
      </h3>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex gap-3 animate-pulse">
              <div className="w-7 h-7 rounded-full bg-gray-800 shrink-0" />
              <div className="flex-1 space-y-1.5 pt-1">
                <div className="h-3 bg-gray-800 rounded w-3/4" />
                <div className="h-2.5 bg-gray-800 rounded w-1/3" />
              </div>
            </div>
          ))}
        </div>
      ) : entries.length === 0 ? (
        <div className="text-center py-8 text-gray-600">
          <Activity size={28} className="mx-auto mb-2 text-gray-700" />
          <p className="text-sm font-cairo">لا يوجد نشاط بعد</p>
          <p className="text-xs text-gray-700 mt-0.5">No activity yet</p>
        </div>
      ) : (
        <div className="relative">
          {/* Vertical line */}
          <div className="absolute right-3.5 top-3 bottom-3 w-px bg-gray-800" />

          <div className="space-y-4">
            {entries.map((entry, idx) => {
              const cfg = getIconConfig(entry.activity_type)
              const Icon = cfg.icon
              return (
                <div key={entry.id} className="flex gap-3 relative">
                  {/* Icon bubble */}
                  <div className={clsx(
                    'w-7 h-7 rounded-full flex items-center justify-center shrink-0 z-10',
                    cfg.bg
                  )}>
                    <Icon size={13} className={cfg.color} />
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0 pt-0.5">
                    <p className="text-sm text-gray-200 font-cairo leading-snug">{entry.summary}</p>
                    <div className="flex items-center gap-1.5 mt-1">
                      {entry.user_name && (
                        <span className="text-xs text-gray-500 font-cairo">{entry.user_name}</span>
                      )}
                      {entry.user_name && <span className="text-gray-700">·</span>}
                      <span className="text-xs text-gray-600">
                        {formatDistanceToNow(new Date(entry.created_at), { addSuffix: true, locale: ar })}
                      </span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
