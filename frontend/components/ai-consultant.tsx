'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'
import { Sparkles, Send, Bot, User, Wand2, FileText, GitBranch, CalendarCheck, FlaskConical, Rocket, Check } from 'lucide-react'
import { onboardingApi } from '@/lib/api'

type Phase = 'chat' | 'building' | 'review'
interface ChatMsg { role: 'user' | 'assistant'; content: string }

const PROFILE_LABELS: Record<string, string> = {
  business_name: 'اسم النشاط', industry: 'المجال', sells: 'ما نبيعه', price_range: 'نطاق الأسعار',
  cities: 'المدن', ideal_customer: 'العميل المثالي', pain_points: 'مشاكل العميل', value_prop: 'قيمة العرض',
  current_sources: 'مصادر العملاء', monthly_lead_target: 'هدف شهري', team_size: 'حجم الفريق', tone: 'نبرة التواصل',
}

const AUTONOMY = [
  { key: 'full', icon: '🤖', title: 'وكيل كامل', desc: 'النظام يعتمد العملاء ويرد ويحجز تلقائياً — تصلك النتائج فقط.' },
  { key: 'copilot', icon: '🤝', title: 'مساعد ذكي', desc: 'الذكاء يؤهّل ويكتب كل شيء، وأنت تعتمد وترسل. (الموصى به)' },
  { key: 'manual', icon: '👤', title: 'يدوي+', desc: 'الذكاء يقيّم وينظّم فقط، وأنت تدير كل التواصل بنفسك.' },
]

export default function AIConsultant() {
  const router = useRouter()
  const [phase, setPhase] = useState<Phase>('chat')
  const [messages, setMessages] = useState<ChatMsg[]>([
    { role: 'assistant', content: 'أهلاً بك في Qualifay! 👋 أنا مستشارك الذكي. أخبرني عن نشاطك التجاري باختصار — ما اسمه، وفي أي مجال تعمل، وماذا تبيع؟' },
  ])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [done, setDone] = useState(false)
  const [profile, setProfile] = useState<Record<string, unknown>>({})
  const [draft, setDraft] = useState<Record<string, any>>({})
  const [autonomy, setAutonomy] = useState('copilot')
  const [applying, setApplying] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }) }, [messages, sending])

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || sending) return
    const next = [...messages, { role: 'user' as const, content: text }]
    setMessages(next)
    setInput('')
    setSending(true)
    try {
      const r = await onboardingApi.chat(next.map((m) => ({ role: m.role, content: m.content })))
      const reply = r.data?.reply || '...'
      setMessages((p) => [...p, { role: 'assistant', content: reply }])
      setProfile(r.data?.profile || {})
      if (r.data?.done) setDone(true)
    } catch { toast.error('تعذّر الاتصال بالمستشار') }
    finally { setSending(false) }
  }, [input, sending, messages])

  async function build() {
    setPhase('building')
    try {
      await onboardingApi.build()
      // Poll for the draft.
      for (let i = 0; i < 20; i++) {
        await new Promise((r) => setTimeout(r, 4000))
        const p = await onboardingApi.profile()
        const bd = p.data?.build_draft
        if (bd && Object.keys(bd).length) { setDraft(bd); setPhase('review'); return }
      }
      toast.error('استغرق البناء وقتاً أطول من المتوقع — حاول مجدداً')
      setPhase('chat')
    } catch { toast.error('فشل بناء النظام'); setPhase('chat') }
  }

  async function apply() {
    setApplying(true)
    try {
      await onboardingApi.apply(draft, autonomy)
      toast.success('🎉 تم بناء نظامك! جاري التحويل إلى لوحة التحكم')
      localStorage.setItem('qualifay_onboarding_done', '1')
      setTimeout(() => router.push('/'), 1200)
    } catch { toast.error('فشل التطبيق'); setApplying(false) }
  }

  async function skip() {
    try { await onboardingApi.skip() } catch { /* mark locally anyway */ }
    localStorage.setItem('qualifay_onboarding_done', '1')
    router.push('/')
  }

  // ── Review screen ──
  if (phase === 'review') {
    const tpls = draft.templates || []
    const steps = (draft.sequence || {}).steps || []
    return (
      <div className="max-w-2xl mx-auto p-4 sm:p-6 space-y-5">
        <div className="text-center">
          <div className="inline-flex items-center gap-2 text-gold-primary mb-1"><Wand2 size={20} /><span className="font-bold font-cairo">هذا ما بنيناه لك</span></div>
          <p className="text-gray-400 text-sm font-cairo">راجع وعدّل ما تشاء، ثم اختر مستوى الأتمتة وابدأ.</p>
        </div>

        {draft.icp?.summary && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="text-xs font-bold text-gold-primary font-cairo mb-1">العميل المثالي</div>
            <p className="text-sm text-gray-300 font-cairo">{draft.icp.summary}</p>
          </div>
        )}

        <Section icon={<FileText size={15} />} title={`قوالب الرسائل (${tpls.length})`}>
          {tpls.map((t: any, i: number) => (
            <textarea key={i} value={t.body || ''} onChange={(e) => { const c = [...tpls]; c[i] = { ...c[i], body: e.target.value }; setDraft({ ...draft, templates: c }) }}
              rows={2} className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-cairo resize-none" />
          ))}
        </Section>

        <Section icon={<GitBranch size={15} />} title={`تسلسل المتابعة (${steps.length} خطوات)`}>
          <div className="flex flex-wrap gap-2">
            {steps.map((s: any, i: number) => (
              <span key={i} className="text-xs bg-gray-800 border border-gray-700 rounded-full px-3 py-1 text-gray-300 font-cairo">
                خطوة {i + 1} · بعد {s.delay_hours || 0} ساعة · {s.channel === 'email' ? 'بريد' : 'واتساب'}
              </span>
            ))}
          </div>
        </Section>

        <div className="grid grid-cols-2 gap-3">
          {draft.flow?.type && <MiniCard icon={<CalendarCheck size={15} />} label="مسار التحويل" value={draft.flow.type} />}
          {draft.ab_test && <MiniCard icon={<FlaskConical size={15} />} label="اختبار A/B" value="افتتاحيتان" />}
        </div>

        <div>
          <div className="text-sm font-bold text-white font-cairo mb-2">كيف تريد أن يعمل النظام؟</div>
          <div className="space-y-2">
            {AUTONOMY.map((a) => (
              <button key={a.key} onClick={() => setAutonomy(a.key)} type="button"
                className={clsx('w-full text-right rounded-xl border p-3 flex items-start gap-3 transition', autonomy === a.key ? 'border-gold-primary bg-gold-primary/10' : 'border-gray-800 hover:border-gray-700')}>
                <span className="text-2xl">{a.icon}</span>
                <span className="flex-1">
                  <span className="block text-sm font-semibold text-white font-cairo">{a.title}</span>
                  <span className="block text-xs text-gray-400 font-cairo mt-0.5">{a.desc}</span>
                </span>
                {autonomy === a.key && <Check size={18} className="text-gold-primary shrink-0" />}
              </button>
            ))}
          </div>
        </div>

        <button onClick={apply} disabled={applying}
          className="w-full flex items-center justify-center gap-2 bg-gold-primary text-gray-950 font-bold py-3.5 rounded-xl disabled:opacity-50 font-cairo">
          <Rocket size={18} /> {applying ? 'جاري البناء...' : 'ابدأ — فعّل نظامي'}
        </button>
      </div>
    )
  }

  // ── Building screen ──
  if (phase === 'building') {
    return (
      <div className="min-h-[70vh] flex flex-col items-center justify-center gap-4 p-6">
        <div className="relative">
          <div className="w-16 h-16 border-4 border-gold-primary/20 border-t-gold-primary rounded-full animate-spin" />
          <Sparkles size={22} className="text-gold-primary absolute inset-0 m-auto" />
        </div>
        <div className="text-center">
          <div className="text-white font-bold font-cairo">نبني نظامك الآن...</div>
          <p className="text-gray-400 text-sm font-cairo mt-1">نصمّم القوالب والتسلسل والحملة بناءً على نشاطك</p>
        </div>
      </div>
    )
  }

  // ── Chat interview ──
  const filled = Object.keys(profile).filter((k) => PROFILE_LABELS[k])
  return (
    <div className="max-w-2xl mx-auto flex flex-col h-[calc(100vh-3rem)]">
      <div className="flex items-center gap-2 p-4 border-b border-gray-800">
        <div className="w-9 h-9 rounded-full bg-gradient-to-br from-gold-primary to-gold-dark flex items-center justify-center"><Sparkles size={18} className="text-gray-950" /></div>
        <div>
          <div className="text-white font-semibold font-cairo text-sm">المستشار الذكي</div>
          <div className="text-[11px] text-gray-500 font-cairo">يفهم نشاطك ليبني لك النظام</div>
        </div>
        <button
          onClick={skip}
          className="mr-auto text-xs text-gray-400 hover:text-white border border-gray-700 hover:border-gray-600 rounded-lg px-3 py-1.5 font-cairo transition-colors"
          title="تخطّي الإعداد والذهاب إلى لوحة التحكم"
        >
          تخطّي ←
        </button>
      </div>

      {filled.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-4 py-2 border-b border-gray-800/60">
          {filled.map((k) => (
            <span key={k} className="text-[10px] bg-gold-primary/10 border border-gold-primary/30 text-gold-primary rounded-full px-2 py-0.5 font-cairo flex items-center gap-1">
              <Check size={9} /> {PROFILE_LABELS[k]}
            </span>
          ))}
        </div>
      )}

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.map((m, i) => (
          <div key={i} className={clsx('flex gap-2', m.role === 'user' ? 'flex-row-reverse' : '')}>
            <div className={clsx('w-7 h-7 rounded-full flex items-center justify-center shrink-0', m.role === 'user' ? 'bg-gray-700' : 'bg-gold-primary/20')}>
              {m.role === 'user' ? <User size={14} className="text-gray-300" /> : <Bot size={14} className="text-gold-primary" />}
            </div>
            <div className={clsx('max-w-[80%] rounded-2xl px-3.5 py-2 text-sm font-cairo whitespace-pre-wrap', m.role === 'user' ? 'bg-gold-primary text-gray-950' : 'bg-gray-800 text-gray-100')}>{m.content}</div>
          </div>
        ))}
        {sending && <div className="flex gap-2"><div className="w-7 h-7 rounded-full bg-gold-primary/20 flex items-center justify-center"><Bot size={14} className="text-gold-primary" /></div><div className="bg-gray-800 rounded-2xl px-4 py-3"><div className="flex gap-1"><span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce" /><span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce [animation-delay:0.15s]" /><span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce [animation-delay:0.3s]" /></div></div></div>}
      </div>

      {done ? (
        <div className="p-4 border-t border-gray-800">
          <button onClick={build} className="w-full flex items-center justify-center gap-2 bg-gold-primary text-gray-950 font-bold py-3 rounded-xl font-cairo">
            <Wand2 size={18} /> ابنِ نظامي الآن
          </button>
        </div>
      ) : (
        <div className="p-3 border-t border-gray-800 flex gap-2">
          <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') send() }}
            placeholder="اكتب إجابتك..." disabled={sending}
            className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo" />
          <button onClick={send} disabled={sending || !input.trim()} className="bg-gold-primary text-gray-950 rounded-xl px-4 disabled:opacity-40"><Send size={16} /></button>
        </div>
      )}
    </div>
  )
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-2">
      <div className="flex items-center gap-1.5 text-xs font-bold text-gold-primary font-cairo">{icon} {title}</div>
      {children}
    </div>
  )
}

function MiniCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-3 flex items-center gap-2">
      <div className="text-gold-primary">{icon}</div>
      <div><div className="text-[11px] text-gray-500 font-cairo">{label}</div><div className="text-sm text-white font-cairo">{value}</div></div>
    </div>
  )
}
