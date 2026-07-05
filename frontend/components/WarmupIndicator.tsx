'use client'

import { clsx } from 'clsx'
import type { WaInstance } from '@/lib/types'

interface WarmupIndicatorProps {
  instance: WaInstance
}

export default function WarmupIndicator({ instance }: WarmupIndicatorProps) {
  const {
    instance_name,
    display_name,
    status,
    day_of_life,
    daily_wa_cap,
    sent_today_wa,
    warmup_complete,
    phone_number,
  } = instance

  const progress = Math.min((day_of_life / 30) * 100, 100)
  const usageRatio = daily_wa_cap > 0 ? sent_today_wa / daily_wa_cap : 0

  const usageColor =
    usageRatio >= 1
      ? 'text-red-400'
      : usageRatio >= 0.8
      ? 'text-yellow-400'
      : 'text-green-400'

  const barColor =
    usageRatio >= 1
      ? 'bg-red-500'
      : usageRatio >= 0.8
      ? 'bg-yellow-400'
      : 'bg-wa-green'

  const isConnected = status === 'connected'

  return (
    <div className="bg-gray-800/50 rounded-lg p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {/* Status dot with pulse */}
          <div className="relative flex items-center justify-center w-3 h-3">
            <span
              className={clsx(
                'absolute inline-flex h-full w-full rounded-full opacity-75',
                isConnected ? 'bg-green-400 animate-ping' : 'bg-red-500'
              )}
            />
            <span
              className={clsx(
                'relative inline-flex rounded-full w-2 h-2',
                isConnected ? 'bg-green-400' : 'bg-red-500'
              )}
            />
          </div>
          <span className="text-sm font-medium text-white font-cairo">
            {display_name || instance_name}
          </span>
        </div>
        <span className="text-xs text-gray-500">{phone_number || '—'}</span>
      </div>

      {/* Warmup status text */}
      <div className="text-xs text-gray-400 font-cairo">
        {warmup_complete ? (
          <span className="text-green-400 font-semibold">✅ جاهز تماماً — {daily_wa_cap} رسالة/يوم</span>
        ) : (
          <span>
            الإحماء (اليوم {day_of_life}/30) — {daily_wa_cap} رسالة/يوم
          </span>
        )}
      </div>

      {/* Day progress bar */}
      {!warmup_complete && (
        <div>
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>التقدم</span>
            <span>{Math.round(progress)}%</span>
          </div>
          <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-gold-primary to-gold-dark rounded-full transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Today's usage */}
      <div>
        <div className="flex justify-between text-xs mb-1">
          <span className="text-gray-500">اليوم</span>
          <span className={usageColor}>
            {sent_today_wa}/{daily_wa_cap}
          </span>
        </div>
        <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
          <div
            className={clsx('h-full rounded-full transition-all', barColor)}
            style={{ width: `${Math.min(usageRatio * 100, 100)}%` }}
          />
        </div>
      </div>
    </div>
  )
}
