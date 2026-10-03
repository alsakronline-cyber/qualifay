'use client'

import useSWR from 'swr'
import { clsx } from 'clsx'
import { format } from 'date-fns'
import { CalendarCheck, ShoppingCart, Phone, FileText, Inbox } from 'lucide-react'
import { flowsApi } from '@/lib/api'

interface Submission {
  id: string; type: string; data: Record<string, unknown>; status: string; lead_id?: string; created_at?: string
}

const META: Record<string, { label: string; icon: React.ReactNode; cls: string }> = {
  booking: { label: 'حجز موعد', icon: <CalendarCheck size={14} />, cls: 'text-gray-400 bg-gray-500/10 border-gray-500/25' },
  order: { label: 'طلب', icon: <ShoppingCart size={14} />, cls: 'text-green-400 bg-green-500/10 border-green-500/25' },
  callback: { label: 'اتصال', icon: <Phone size={14} />, cls: 'text-gray-400 bg-gray-500/10 border-gray-500/25' },
  quote: { label: 'عرض سعر', icon: <FileText size={14} />, cls: 'text-gray-400 bg-gray-500/10 border-gray-500/25' },
  custom: { label: 'أخرى', icon: <FileText size={14} />, cls: 'text-gray-400 bg-gray-700 border-gray-600' },
}

function summary(s: Submission): string {
  const d = s.data || {}
  if (s.type === 'booking') return String(d.datetime || '—')
  if (s.type === 'order') {
    const items = (d.items as { name: string; qty: number }[]) || []
    const line = items.map((i) => `${i.name}×${i.qty}`).join('، ')
    return line + (d.total ? ` — ${d.total}` : '')
  }
  if (s.type === 'callback') return String(d.preferred_time || '—')
  return String(d.notes || '—')
}

export default function SubmissionsPage() {
  const { data, isLoading } = useSWR('flow-submissions', () => flowsApi.submissions().then((r) => r.data), { refreshInterval: 20000 })
  const subs: Submission[] = Array.isArray(data) ? data : []

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white font-cairo">الطلبات والحجوزات</h1>
        <p className="text-gray-400 text-sm mt-1">Conversions — الحجوزات والطلبات وعروض الأسعار المؤكدة</p>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" /></div>
      ) : subs.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          <Inbox size={40} className="mx-auto mb-3 text-gray-700" />
          <p className="font-cairo">لا توجد تحويلات بعد</p>
          <p className="text-xs text-gray-600 mt-1">أنشئ إجراءً من داخل المحادثة (زر "إجراء")</p>
        </div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="text-right px-4 py-3 text-xs font-semibold text-gray-400 font-cairo">النوع</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-gray-400 font-cairo">التفاصيل</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-gray-400 font-cairo">الحالة</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-gray-400 font-cairo">التاريخ</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {subs.map((s) => {
                const m = META[s.type] || META.custom
                return (
                  <tr key={s.id} className="hover:bg-gray-800/50 transition-colors">
                    <td className="px-4 py-3">
                      <span className={clsx('inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded border font-cairo', m.cls)}>{m.icon} {m.label}</span>
                    </td>
                    <td className="px-4 py-3 text-gray-200 font-cairo">{summary(s)}</td>
                    <td className="px-4 py-3 text-gray-400 font-cairo">{s.status === 'confirmed' ? 'مؤكد' : s.status}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{s.created_at ? format(new Date(s.created_at), 'yyyy-MM-dd HH:mm') : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
