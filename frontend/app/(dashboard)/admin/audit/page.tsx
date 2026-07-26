'use client'

import useSWR from 'swr'
import { ScrollText, User, Building2, KeyRound, Trash2, LogIn, Settings2 } from 'lucide-react'
import { adminApi } from '@/lib/api'
import { formatDistanceToNow } from 'date-fns'
import { ar } from 'date-fns/locale'

interface Entry {
  id: string; actor_email: string; action: string; target_type: string | null
  target_label: string | null; detail: Record<string, unknown> | null; created_at: string | null
}

const ACTION: Record<string, { label: string; icon: React.ComponentType<{ size?: number; className?: string }>; cls: string }> = {
  'tenant.update': { label: 'تعديل شركة', icon: Building2, cls: 'text-blue-400' },
  'user.update': { label: 'تعديل حساب', icon: Settings2, cls: 'text-gold-primary' },
  'user.set_password': { label: 'تغيير كلمة مرور', icon: KeyRound, cls: 'text-yellow-400' },
  'user.delete': { label: 'حذف حساب', icon: Trash2, cls: 'text-red-400' },
  'impersonate': { label: 'دخول كشركة', icon: LogIn, cls: 'text-purple-400' },
}

export default function AdminAuditPage() {
  const { data } = useSWR('admin-audit', () => adminApi.audit().then((r) => r.data), { refreshInterval: 30000 })
  const rows: Entry[] = Array.isArray(data) ? data : []

  return (
    <div className="space-y-5 max-w-3xl">
      <div className="flex items-center gap-2">
        <ScrollText size={20} className="text-gold-primary" />
        <div><h1 className="text-2xl font-bold text-white font-cairo">سجل الإجراءات</h1><p className="text-gray-400 text-sm font-cairo">كل إجراءات المالك على المنصة</p></div>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl divide-y divide-gray-800">
        {rows.map((e) => {
          const a = ACTION[e.action] || { label: e.action, icon: User, cls: 'text-gray-400' }
          const Icon = a.icon
          const det = e.detail && Object.keys(e.detail).length
            ? Object.entries(e.detail).map(([k, v]) => `${k}: ${v}`).join(' · ') : ''
          return (
            <div key={e.id} className="flex items-start gap-3 px-4 py-3">
              <Icon size={16} className={`${a.cls} mt-0.5 shrink-0`} />
              <div className="flex-1 min-w-0">
                <div className="text-sm text-white font-cairo">
                  {a.label}{e.target_label && <> — <span className="text-gray-300" dir="ltr">{e.target_label}</span></>}
                </div>
                {det && <div className="text-xs text-gray-500 truncate" dir="ltr">{det}</div>}
                <div className="text-[11px] text-gray-600 font-cairo mt-0.5">
                  بواسطة <span dir="ltr">{e.actor_email}</span>
                  {e.created_at && <> · {formatDistanceToNow(new Date(e.created_at), { addSuffix: true, locale: ar })}</>}
                </div>
              </div>
            </div>
          )
        })}
        {rows.length === 0 && <p className="text-center text-gray-600 text-sm py-8 font-cairo">لا إجراءات مسجّلة بعد</p>}
      </div>
    </div>
  )
}
