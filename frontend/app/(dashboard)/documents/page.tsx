'use client'

import { useState } from 'react'
import useSWR from 'swr'
import Link from 'next/link'
import { clsx } from 'clsx'
import { FileText, Plus, FileSpreadsheet, ClipboardList, Receipt, ScrollText } from 'lucide-react'
import { salesApi } from '@/lib/api'

export const DOC_TYPES = [
  { key: 'inquiry', label: 'طلبات الأسعار', icon: ClipboardList },
  { key: 'quotation', label: 'عروض الأسعار', icon: FileSpreadsheet },
  { key: 'sales_order', label: 'أوامر البيع', icon: ScrollText },
  { key: 'invoice', label: 'الفواتير', icon: Receipt },
] as const

export const DOC_LABEL: Record<string, string> = {
  inquiry: 'طلب عرض سعر', quotation: 'عرض سعر', sales_order: 'أمر بيع', invoice: 'فاتورة',
}
export const STATUS_LABEL: Record<string, string> = {
  draft: 'مسودة', sent: 'مُرسل', accepted: 'مقبول', rejected: 'مرفوض', paid: 'مدفوع', cancelled: 'ملغي',
}
export const STATUS_COLOR: Record<string, string> = {
  draft: 'bg-gray-500/10 text-gray-400', sent: 'bg-gray-500/10 text-gray-400',
  accepted: 'bg-green-500/10 text-green-400', rejected: 'bg-red-500/10 text-red-400',
  paid: 'bg-wa-green/10 text-wa-green', cancelled: 'bg-gray-600/10 text-gray-500',
}

interface Doc {
  id: string; doc_type: string; number: string; status: string
  customer_company?: string; customer_name?: string; currency: string
  grand_total: number; issue_date?: string; created_at?: string
}

export default function DocumentsPage() {
  const [tab, setTab] = useState<string>('quotation')
  const { data, isLoading } = useSWR(['sales', tab], () =>
    salesApi.list({ doc_type: tab }).then((r) => r.data as Doc[]))
  const docs: Doc[] = Array.isArray(data) ? data : []

  return (
    <div className="space-y-5 max-w-5xl">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <FileText size={22} className="text-gold-primary" />
          <div>
            <h1 className="text-2xl font-bold text-white font-cairo">المستندات</h1>
            <p className="text-gray-400 text-sm font-cairo">عروض الأسعار، أوامر البيع، والفواتير</p>
          </div>
        </div>
        <Link href={`/documents/new?type=${tab}`}
          className="flex items-center gap-1.5 bg-gold-primary text-gray-950 font-semibold text-sm px-4 py-2 rounded-lg font-cairo">
          <Plus size={16} /> {DOC_LABEL[tab]} جديد
        </Link>
      </div>

      {/* Type tabs */}
      <div className="flex gap-2 border-b border-gray-800 overflow-x-auto">
        {DOC_TYPES.map((t) => {
          const Icon = t.icon
          return (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={clsx('flex items-center gap-1.5 px-4 py-2.5 text-sm font-cairo border-b-2 -mb-px whitespace-nowrap transition-colors',
                tab === t.key ? 'border-gold-primary text-gold-primary' : 'border-transparent text-gray-400 hover:text-gray-200')}>
              <Icon size={15} /> {t.label}
            </button>
          )
        })}
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" /></div>
      ) : docs.length === 0 ? (
        <div className="text-center py-16 text-gray-500 font-cairo">
          لا توجد مستندات بعد. <Link href={`/documents/new?type=${tab}`} className="text-gold-primary hover:underline">أنشئ {DOC_LABEL[tab]}</Link>
        </div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-800/50 text-gray-400 font-cairo text-xs">
              <tr>
                <th className="text-right px-4 py-2.5">الرقم</th>
                <th className="text-right px-4 py-2.5">العميل</th>
                <th className="text-right px-4 py-2.5">التاريخ</th>
                <th className="text-left px-4 py-2.5">الإجمالي</th>
                <th className="text-center px-4 py-2.5">الحالة</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id} className="border-t border-gray-800 hover:bg-gray-800/40">
                  <td className="px-4 py-3">
                    <Link href={`/documents/${d.id}`} className="text-gold-primary font-mono hover:underline">{d.number}</Link>
                  </td>
                  <td className="px-4 py-3 text-white font-cairo">{d.customer_company || d.customer_name || '—'}</td>
                  <td className="px-4 py-3 text-gray-400">{d.issue_date ? new Date(d.issue_date).toLocaleDateString('ar-EG') : '—'}</td>
                  <td className="px-4 py-3 text-left text-white font-mono">{d.grand_total?.toLocaleString()} {d.currency}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={clsx('text-xs px-2 py-0.5 rounded-full font-cairo', STATUS_COLOR[d.status] || 'bg-gray-700 text-gray-400')}>
                      {STATUS_LABEL[d.status] || d.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
