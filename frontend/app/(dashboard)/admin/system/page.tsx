'use client'

import useSWR from 'swr'
import { clsx } from 'clsx'
import { Activity, Database, Server, Smartphone, HardDrive, DatabaseBackup, CheckCircle2, XCircle, CreditCard } from 'lucide-react'
import { adminApi } from '@/lib/api'
import { formatDistanceToNow } from 'date-fns'
import { ar } from 'date-fns/locale'

function StatusDot({ ok }: { ok: boolean }) {
  return ok ? <CheckCircle2 size={16} className="text-green-400" /> : <XCircle size={16} className="text-red-400" />
}

function Row({ icon: Icon, label, value, ok }: { icon: React.ComponentType<{ size?: number; className?: string }>; label: string; value: string; ok: boolean }) {
  return (
    <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-800 last:border-0">
      <Icon size={16} className="text-gray-400 shrink-0" />
      <span className="text-sm text-gray-200 font-cairo flex-1">{label}</span>
      <span className={clsx('text-xs font-mono', ok ? 'text-gray-400' : 'text-red-400')} dir="ltr">{value}</span>
      <StatusDot ok={ok} />
    </div>
  )
}

export default function AdminSystemPage() {
  const { data: sys } = useSWR('admin-system', () => adminApi.system().then((r) => r.data), { refreshInterval: 30000 })
  const { data: inst } = useSWR('admin-instances', () => adminApi.instances().then((r) => r.data))
  const { data: plans } = useSWR('admin-plans', () => adminApi.plans().then((r) => r.data))
  const s = sys || {}
  const instances: Array<{ id: string; instance_name: string; company: string; status: string; day_of_life: number; daily_wa_cap: number; sent_today_wa: number }> = Array.isArray(inst) ? inst : []
  const bk = s.last_backup

  const okStr = (v: unknown) => typeof v === 'string' && v === 'ok'

  return (
    <div className="space-y-5 max-w-4xl">
      <div className="flex items-center gap-2">
        <Activity size={20} className="text-gold-primary" />
        <div><h1 className="text-2xl font-bold text-white font-cairo">صحة النظام</h1><p className="text-gray-400 text-sm font-cairo">حالة الخدمات والنسخ الاحتياطي</p></div>
      </div>

      {/* Services */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <Row icon={Database} label="قاعدة البيانات" value={String(s.database ?? '…')} ok={okStr(s.database)} />
        <Row icon={Server} label="Redis" value={String(s.redis ?? '…')} ok={okStr(s.redis)} />
        <Row icon={Smartphone} label="بوابة واتساب (Evolution)" value={String(s.evolution_api ?? '…')} ok={okStr(s.evolution_api)} />
      </div>

      {/* Backup + disk */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2"><DatabaseBackup size={16} className="text-gold-primary" /><h2 className="text-sm font-bold text-white font-cairo">آخر نسخة احتياطية</h2></div>
          {bk && bk.at ? (
            <div className="text-sm text-gray-300 font-cairo space-y-0.5">
              <div>منذ {formatDistanceToNow(new Date(bk.at), { locale: ar })}</div>
              <div className="text-xs text-gray-500" dir="ltr">{bk.file} · {bk.size_kb} KB · {bk.count} نسخة</div>
            </div>
          ) : <div className="text-sm text-red-400 font-cairo">لا توجد نسخة احتياطية!</div>}
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2"><HardDrive size={16} className="text-gold-primary" /><h2 className="text-sm font-bold text-white font-cairo">القرص</h2></div>
          {s.disk ? (
            <>
              <div className="text-sm text-gray-300 font-cairo mb-1.5">{s.disk.used_gb} / {s.disk.total_gb} GB ({s.disk.pct}%)</div>
              <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                <div className={clsx('h-full rounded-full', s.disk.pct > 85 ? 'bg-red-500' : 'bg-gold-primary')} style={{ width: `${s.disk.pct}%` }} />
              </div>
            </>
          ) : <div className="text-sm text-gray-500">—</div>}
        </div>
      </div>

      {/* Plans */}
      {plans && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3"><CreditCard size={16} className="text-gold-primary" /><h2 className="text-sm font-bold text-white font-cairo">الخطط</h2>
            <span className="text-xs text-gray-500 mr-auto font-cairo">{plans.paying_tenants} مدفوعة · {plans.trial_tenants} تجربة</span></div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(plans.by_plan || {}).map(([p, n]) => (
              <span key={p} className="text-xs bg-gray-800 border border-gray-700 rounded-full px-3 py-1 text-gray-300 font-cairo">{p}: {n as number}</span>
            ))}
          </div>
        </div>
      )}

      {/* Platform WhatsApp instances */}
      <div>
        <div className="flex items-center gap-2 mb-2"><Smartphone size={16} className="text-gold-primary" /><h2 className="text-sm font-bold text-white font-cairo">أجهزة واتساب (كل المنصة)</h2></div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl divide-y divide-gray-800">
          {instances.map((i) => {
            const connected = ['connected', 'open'].includes(i.status)
            return (
              <div key={i.id} className="flex items-center gap-3 px-4 py-2.5">
                <StatusDot ok={connected} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-white font-cairo truncate">{i.instance_name} <span className="text-gray-500 text-xs">· {i.company}</span></div>
                </div>
                <span className="text-xs text-gray-400 font-cairo">يوم {i.day_of_life || 0}</span>
                <span className="text-xs text-gray-400 font-cairo">{i.sent_today_wa || 0}/{i.daily_wa_cap || 0}</span>
                <span className={clsx('text-[11px] px-2 py-0.5 rounded-full font-cairo', connected ? 'text-green-400 bg-green-500/10' : 'text-gray-400 bg-gray-700')}>{i.status}</span>
              </div>
            )
          })}
          {instances.length === 0 && <p className="text-center text-gray-600 text-sm py-6 font-cairo">لا توجد أجهزة</p>}
        </div>
      </div>
    </div>
  )
}
