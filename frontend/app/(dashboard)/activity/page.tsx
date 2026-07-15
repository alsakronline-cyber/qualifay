'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'
import { formatDistanceToNow } from 'date-fns'
import { ar } from 'date-fns/locale'
import { Sparkles, RefreshCw, Send, MessageSquareReply, Users, AlertTriangle, CheckCircle2, Zap, Brain, Trophy, ShieldAlert, Lightbulb } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { agentRunsApi } from '@/lib/api'

interface Memory { id: string; kind: string; content: string; weight: number }
const MEM_KIND: Record<string, { label: string; icon: LucideIcon; cls: string }> = {
  win_reason: { label: 'يكسب العملاء', icon: Trophy, cls: 'text-green-400' },
  loss_reason: { label: 'يخسر العملاء', icon: ShieldAlert, cls: 'text-red-400' },
  objection: { label: 'اعتراض شائع', icon: AlertTriangle, cls: 'text-yellow-400' },
  insight: { label: 'ملاحظة', icon: Lightbulb, cls: 'text-blue-400' },
}

function MemoryPanel() {
  const { data } = useSWR('agent-memory', () => agentRunsApi.memory().then((r) => r.data))
  const mems: Memory[] = data?.items || []
  if (mems.length === 0) return null
  return (
    <div className="bg-gray-900 border border-gold-primary/20 rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Brain size={17} className="text-gold-primary" />
        <h2 className="text-sm font-bold text-white font-cairo">ما تعلّمه نظامك عن سوقك</h2>
        <span className="text-[11px] text-gray-500 mr-auto font-cairo">{mems.length} درس</span>
      </div>
      <div className="space-y-2">
        {mems.map((m) => {
          const k = MEM_KIND[m.kind] || MEM_KIND.insight
          const Icon = k.icon
          return (
            <div key={m.id} className="flex items-start gap-2 text-sm">
              <Icon size={13} className={clsx('mt-0.5 shrink-0', k.cls)} />
              <span className="text-gray-300 font-cairo flex-1">{m.content}</span>
              {m.weight > 1 && <span className="text-[10px] text-gold-primary/70 bg-gold-primary/10 rounded-full px-1.5 shrink-0">×{m.weight}</span>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

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

      <MemoryPanel />

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
