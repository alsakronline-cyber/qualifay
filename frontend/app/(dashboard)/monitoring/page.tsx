'use client'

import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { Activity, Database, Server, Cpu, HardDrive, DownloadCloud, CheckCircle2, XCircle } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { monitoringApi } from '@/lib/api'

interface Svc { ok: boolean; error?: string; status?: number; workers?: number }
interface Health {
  healthy: boolean
  services: { database: Svc; redis: Svc; evolution_api: Svc; celery: Svc }
  disk?: { free_gb: number; total_gb: number; used_pct: number } | null
  last_backup?: { file: string; size: number; at: string; count: number } | null
}

const LABELS: Record<string, { label: string; icon: LucideIcon }> = {
  database: { label: 'قاعدة البيانات', icon: Database },
  redis: { label: 'Redis (الطابور)', icon: Cpu },
  evolution_api: { label: 'واتساب (Evolution)', icon: Server },
  celery: { label: 'العمّال (Celery)', icon: Activity },
}

function Pill({ ok }: { ok: boolean }) {
  return (
    <span className={clsx('inline-flex items-center gap-1 text-xs font-cairo', ok ? 'text-green-400' : 'text-red-400')}>
      {ok ? <CheckCircle2 size={14} /> : <XCircle size={14} />} {ok ? 'يعمل' : 'متوقف'}
    </span>
  )
}

export default function MonitoringPage() {
  const { data, mutate, isLoading } = useSWR<Health>('monitoring', () => monitoringApi.health().then((r) => r.data), { refreshInterval: 30000 })

  async function backup() {
    try { await monitoringApi.runBackup(); toast.success('بدأ النسخ الاحتياطي — سيظهر خلال دقيقة') }
    catch (e: unknown) { const err = e as { response?: { data?: { detail?: string } } }; toast.error(err?.response?.data?.detail || 'فشل') }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white font-cairo flex items-center gap-2"><Activity size={22} /> المراقبة</h1>
          <p className="text-gray-400 text-sm mt-1">حالة الخدمات والنسخ الاحتياطي</p>
        </div>
        <button onClick={backup} className="flex items-center gap-1.5 bg-gold-primary text-gray-950 font-semibold text-sm px-4 py-2 rounded-lg font-cairo">
          <DownloadCloud size={16} /> نسخ احتياطي الآن
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" /></div>
      ) : !data ? (
        <div className="text-center py-16 text-gray-500 font-cairo">تعذّر تحميل الحالة</div>
      ) : (
        <>
          <div className={clsx('rounded-xl border px-4 py-3 font-cairo text-sm flex items-center gap-2',
            data.healthy ? 'border-green-500/30 bg-green-500/10 text-green-300' : 'border-red-500/30 bg-red-500/10 text-red-300')}>
            {data.healthy ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
            {data.healthy ? 'جميع الأنظمة تعمل بشكل طبيعي' : 'هناك خدمة أو أكثر بها مشكلة'}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {(Object.keys(LABELS) as Array<keyof typeof data.services>).map((k) => {
              const svc = data.services[k]; const meta = LABELS[k]; const Icon = meta.icon
              return (
                <div key={k} className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex items-center gap-3">
                  <div className={clsx('w-10 h-10 rounded-lg flex items-center justify-center', svc.ok ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400')}><Icon size={18} /></div>
                  <div className="flex-1">
                    <div className="text-sm font-medium text-white font-cairo">{meta.label}</div>
                    {svc.error && <div className="text-[11px] text-red-400/70 truncate max-w-[220px]" dir="ltr">{svc.error}</div>}
                    {k === 'celery' && svc.ok && <div className="text-[11px] text-gray-500 font-cairo">{svc.workers} عامل نشط</div>}
                  </div>
                  <Pill ok={svc.ok} />
                </div>
              )
            })}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {data.disk && (
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <div className="flex items-center gap-2 text-sm text-white font-cairo mb-2"><HardDrive size={16} /> القرص</div>
                <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                  <div className={clsx('h-full', data.disk.used_pct > 85 ? 'bg-red-500' : 'bg-gold-primary')} style={{ width: `${data.disk.used_pct}%` }} />
                </div>
                <div className="text-xs text-gray-400 mt-1.5 font-cairo">{data.disk.free_gb} GB متاح من {data.disk.total_gb} GB · مستخدم {data.disk.used_pct}%</div>
              </div>
            )}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <div className="flex items-center gap-2 text-sm text-white font-cairo mb-2"><DownloadCloud size={16} /> آخر نسخة احتياطية</div>
              {data.last_backup ? (
                <div className="text-xs text-gray-400 font-cairo space-y-0.5">
                  <div dir="ltr" className="text-gray-300">{data.last_backup.file}</div>
                  <div>{new Date(data.last_backup.at).toLocaleString('ar-EG')} · {(data.last_backup.size / 1e6).toFixed(1)} MB</div>
                  <div>{data.last_backup.count} نسخة محفوظة</div>
                </div>
              ) : <div className="text-xs text-gray-500 font-cairo">لا توجد نسخ بعد</div>}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
