'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'
import { formatDistanceToNow } from 'date-fns'
import { ar } from 'date-fns/locale'
import { Sparkles, RefreshCw, Send, MessageSquareReply, Users, AlertTriangle, CheckCircle2, Zap } from 'lucide-react'
import { agentRunsApi } from '@/lib/api'

interface Action { type: string; detail: string }
interface Metrics { sent_24h?: number; replies_24h?: number; pending_review?: number; cold_leads?: number; wa_near_cap?: number }
interface Run { id: string; kind: string; status: string; summary: string; actions: Action[]; metrics: Metrics; created_at: string }

const STATUS = {
  acted: { label: 'اتخذ إجراءً', cls: 'text-green-400 bg-green-500/10 border-green-500/30', icon: Zap },
  alerted: { label: 'تنبيه', cls: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30', icon: AlertTriangle },
  idle: { label: 'مراقبة', cls: 'text-gray-400 bg-gray-700 border-gray-600', icon: CheckCircle2 },
} as const

export default function ActivityPage() {
  const { data, mutate, isLoading } = useSWR('agent-runs', () => agentRunsApi.list().then((r) => r.data), { refreshInterval: 60000 })
  const runs: Run[] = data?.items || []
  const [running, setRunning] = useState(false)

  async function runNow() {
    setRunning(true)
    try {
      await agentRunsApi.runNow()
      toast.success('يعمل المستشار الآن — حدّث بعد لحظات')
      setTimeout(() => { mutate(); setRunning(false) }, 6000)
    } catch { toast.error('فشل'); setRunning(false) }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white font-cairo flex items-center gap-2"><Sparkles size={22} /> نشاط المساعد الذكي</h1>
          <p className="text-gray-400 text-sm mt-1">ماذا فعل نظامك تلقائياً — كل دورة قرار مسجّلة</p>
        </div>
        <button onClick={runNow} disabled={running} className="flex items-center gap-1.5 bg-gold-primary text-gray-950 font-semibold text-sm px-4 py-2 rounded-lg disabled:opacity-50 font-cairo">
          <RefreshCw size={15} className={running ? 'animate-spin' : ''} /> شغّل الآن
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" /></div>
      ) : runs.length === 0 ? (
        <div className="text-center py-16 text-gray-500 font-cairo">لا يوجد نشاط بعد. يعمل المساعد تلقائياً كل ١٥ دقيقة — أو اضغط "شغّل الآن".</div>
      ) : (
        <div className="relative pr-4">
          <div className="absolute right-1.5 top-2 bottom-2 w-px bg-gray-800" />
          <div className="space-y-3">
            {runs.map((r) => {
              const st = STATUS[r.status as keyof typeof STATUS] || STATUS.idle
              const Icon = st.icon
              return (
                <div key={r.id} className="relative pr-6">
                  <div className={clsx('absolute right-0 top-3 w-3 h-3 rounded-full border-2 border-gray-950', st.cls.split(' ')[1])} />
                  <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <span className={clsx('inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border font-cairo', st.cls)}>
                        <Icon size={11} /> {st.label}
                      </span>
                      <span className="text-[11px] text-gray-500 mr-auto font-cairo">{r.created_at ? formatDistanceToNow(new Date(r.created_at), { addSuffix: true, locale: ar }) : ''}</span>
                    </div>
                    <p className="text-sm text-gray-200 font-cairo leading-relaxed">{r.summary}</p>

                    {r.actions?.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {r.actions.map((a, i) => (
                          <div key={i} className="flex items-center gap-1.5 text-xs text-gold-primary/90 font-cairo">
                            <Zap size={11} /> {a.detail}
                          </div>
                        ))}
                      </div>
                    )}

                    <div className="flex flex-wrap gap-3 mt-3 pt-2 border-t border-gray-800 text-[11px] text-gray-400 font-cairo">
                      <span className="flex items-center gap-1"><Send size={11} /> {r.metrics?.sent_24h ?? 0} مُرسل</span>
                      <span className="flex items-center gap-1"><MessageSquareReply size={11} /> {r.metrics?.replies_24h ?? 0} رد</span>
                      {!!r.metrics?.pending_review && <span className="flex items-center gap-1"><Users size={11} /> {r.metrics.pending_review} للمراجعة</span>}
                      {!!r.metrics?.cold_leads && <span className="text-yellow-500/80">{r.metrics.cold_leads} بارد</span>}
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
