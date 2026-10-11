'use client'

import useSWR from 'swr'
import Link from 'next/link'
import { clsx } from 'clsx'
import {
  CheckCircle2, MessageSquare, WifiOff, Smartphone, Mail, Search, ArrowLeft,
  Send, Clock, Circle, PartyPopper,
} from 'lucide-react'
import { dashboardApi } from '@/lib/api'

type Icon = React.ComponentType<{ size?: number; className?: string }>

interface NumberRow {
  id: string
  name: string
  phone?: string | null
  state: 'active' | 'warming' | 'quiet' | 'paused' | 'disconnected'
  day: number
  quiet_days_left: number
  sent_today: number
  daily_limit: number
}

interface Home {
  attention: { pending_review: number; unanswered: number; disconnected: string[] }
  today: { whatsapp_sent: number; whatsapp_limit: number; email_sent: number; email_limit: number; next_run: string }
  numbers: NumberRow[]
  week: { contacted: number; replied: number; booked: number; won: number }
  setup: { whatsapp: boolean; email: boolean; leads: boolean }
  total_leads: number
  trial_ends_at: string | null
  plan: string | null
}

// What each number state means, in the client's words — so "not sending" never looks broken.
const STATE: Record<NumberRow['state'], { label: string; tone: string; hint: (n: NumberRow) => string }> = {
  active: { label: 'نشط', tone: 'text-green-400 bg-green-500/10 border-green-500/30',
    hint: (n) => `أرسل ${n.sent_today} من ${n.daily_limit} اليوم` },
  warming: { label: 'يزيد تدريجياً', tone: 'text-sky-400 bg-sky-500/10 border-sky-500/30',
    hint: (n) => `حد يومي مخفّض (${n.daily_limit}) لحماية الرقم — أرسل ${n.sent_today} اليوم` },
  quiet: { label: 'فترة الحماية', tone: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
    hint: (n) => `رقم جديد: يرد على الرسائل فقط — تبدأ الحملات بعد ${n.quiet_days_left} يوم` },
  paused: { label: 'متوقف مؤقتاً', tone: 'text-gray-300 bg-gray-500/10 border-gray-500/30',
    hint: () => 'لا يرسل حملات — الردود في صندوق الوارد تعمل' },
  disconnected: { label: 'غير متصل', tone: 'text-red-400 bg-red-500/10 border-red-500/30',
    hint: () => 'أعد ربط الرقم لاستئناف الإرسال والردود' },
}

function AttentionCard({ href, icon: I, count, title, cta, tone }: {
  href: string; icon: Icon; count: number | string; title: string; cta: string; tone: string
}) {
  return (
    <Link href={href} className={clsx('group flex items-center gap-3 rounded-xl border p-4 transition-colors hover:bg-gray-800/60', tone)}>
      <I size={20} className="shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-white font-cairo">
          <span className="text-lg font-bold me-1">{count}</span>{title}
        </div>
        <div className="text-xs font-cairo opacity-80 mt-0.5">{cta}</div>
      </div>
      <ArrowLeft size={16} className="shrink-0 opacity-60 group-hover:opacity-100 rtl:rotate-0 ltr:rotate-180" />
    </Link>
  )
}

function Meter({ icon: I, label, sent, limit, empty }: { icon: Icon; label: string; sent: number; limit: number; empty: string }) {
  const pct = limit > 0 ? Math.min(100, (sent / limit) * 100) : 0
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <div className="flex items-center gap-2 text-sm text-gray-400 font-cairo">
        <I size={16} /> {label}
      </div>
      {limit > 0 ? (
        <>
          <div className="mt-2 text-2xl font-bold text-white">
            {sent}<span className="text-sm text-gray-500 font-normal"> / {limit}</span>
          </div>
          <div className="mt-2 h-1.5 bg-gray-800 rounded-full overflow-hidden" role="progressbar"
            aria-valuenow={sent} aria-valuemin={0} aria-valuemax={limit}>
            <div className="h-full bg-gold-primary rounded-full" style={{ width: `${pct}%` }} />
          </div>
        </>
      ) : (
        <p className="mt-2 text-xs text-gray-500 font-cairo leading-relaxed">{empty}</p>
      )}
    </div>
  )
}

function Funnel({ week }: { week: Home['week'] }) {
  const steps = [
    { k: 'contacted', label: 'تم التواصل' },
    { k: 'replied', label: 'ردّوا' },
    { k: 'booked', label: 'مواعيد / عروض' },
    { k: 'won', label: 'صفقات' },
  ] as const
  const max = Math.max(week.contacted, 1)
  return (
    <div className="space-y-2.5">
      {steps.map((s) => {
        const v = week[s.k]
        return (
          <div key={s.k} className="flex items-center gap-3">
            <span className="w-28 shrink-0 text-xs text-gray-400 font-cairo">{s.label}</span>
            <div className="flex-1 h-6 bg-gray-800/60 rounded-md overflow-hidden">
              <div className="h-full bg-gold-primary/70 rounded-md" style={{ width: `${Math.max((v / max) * 100, v ? 3 : 0)}%` }} />
            </div>
            <span className="w-10 text-end text-sm font-semibold text-white tabular-nums">{v}</span>
          </div>
        )
      })}
    </div>
  )
}

function SetupChecklist({ setup }: { setup: Home['setup'] }) {
  const steps = [
    { done: setup.whatsapp, href: '/instances', icon: Smartphone, title: 'اربط رقم واتساب', hint: 'من صفحة أرقام واتساب — بمسح QR أو برقم الهاتف' },
    { done: setup.email, href: '/email-accounts', icon: Mail, title: 'اربط بريدك الإلكتروني', hint: 'لإرسال الحملات من عنوان شركتك' },
    { done: setup.leads, href: '/scrape', icon: Search, title: 'اجمع أو استورد أول عملاء', hint: 'ابحث في خرائط جوجل أو ارفع ملف جهات اتصال' },
  ]
  const doneCount = steps.filter((s) => s.done).length
  return (
    <section className="bg-gradient-to-l from-gold-primary/10 to-transparent border border-gold-primary/20 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-bold text-white font-cairo">جهّز حسابك</h2>
        <span className="text-xs text-gray-400 font-cairo">{doneCount} من 3</span>
      </div>
      <ol className="space-y-2">
        {steps.map((s) => (
          <li key={s.href}>
            <Link href={s.href} className={clsx('flex items-center gap-3 rounded-lg p-2 -mx-2 hover:bg-gray-800/60', s.done && 'opacity-60')}>
              {s.done ? <CheckCircle2 size={18} className="text-green-400 shrink-0" /> : <Circle size={18} className="text-gray-600 shrink-0" />}
              <div className="min-w-0">
                <div className={clsx('text-sm font-cairo', s.done ? 'text-gray-400 line-through' : 'text-white font-semibold')}>{s.title}</div>
                {!s.done && <div className="text-xs text-gray-500 font-cairo">{s.hint}</div>}
              </div>
            </Link>
          </li>
        ))}
      </ol>
    </section>
  )
}

function Skeleton() {
  return (
    <div className="space-y-4 max-w-5xl mx-auto animate-pulse" aria-busy="true">
      <div className="h-8 w-56 bg-gray-800 rounded" />
      <div className="grid sm:grid-cols-3 gap-3">{[0, 1, 2].map((i) => <div key={i} className="h-20 bg-gray-900 rounded-xl" />)}</div>
      <div className="grid sm:grid-cols-3 gap-3">{[0, 1, 2].map((i) => <div key={i} className="h-28 bg-gray-900 rounded-xl" />)}</div>
      <div className="h-48 bg-gray-900 rounded-xl" />
    </div>
  )
}

function cairoTime(iso: string) {
  try {
    const d = new Date(iso)
    const today = new Date().toDateString() === d.toDateString()
    const t = d.toLocaleTimeString('ar-EG', { hour: 'numeric', minute: '2-digit', timeZone: 'Africa/Cairo' })
    return `${today ? 'اليوم' : 'غداً'} ${t}`
  } catch { return '' }
}

export default function DashboardPage() {
  const { data, error } = useSWR<Home>('/dashboard/home', () => dashboardApi.home().then((r) => r.data),
    { refreshInterval: 60000 })

  if (error && !data) {
    return (
      <div className="max-w-md mx-auto text-center py-16">
        <p className="text-white font-cairo font-semibold">تعذّر تحميل لوحة التحكم</p>
        <p className="text-sm text-gray-400 font-cairo mt-1">تحقق من اتصالك ثم حدّث الصفحة.</p>
      </div>
    )
  }
  if (!data) return <Skeleton />

  const { attention, today, numbers, week, setup } = data
  const setupDone = setup.whatsapp && setup.email && setup.leads
  const trialDays = data.trial_ends_at
    ? Math.ceil((new Date(data.trial_ends_at).getTime() - Date.now()) / 86400000) : null
  const allClear = !attention.pending_review && !attention.unanswered && !attention.disconnected.length
  const replyRate = week.contacted ? Math.round((week.replied / week.contacted) * 100) : 0

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold text-white font-cairo">لوحة التحكم</h1>
          <p className="text-sm text-gray-400 font-cairo mt-1">ما يحتاج انتباهك، وما أنجزه النظام اليوم.</p>
        </div>
        {trialDays !== null && trialDays >= 0 && trialDays <= 30 && (
          <Link href="/billing" className="text-xs font-cairo text-gold-primary border border-gold-primary/30 bg-gold-primary/10 rounded-full px-3 py-1 hover:bg-gold-primary/20">
            متبقٍ {trialDays} يوم في الفترة التجريبية
          </Link>
        )}
      </header>

      {!setupDone && <SetupChecklist setup={setup} />}

      {/* Needs you now */}
      <section aria-labelledby="att">
        <h2 id="att" className="text-sm font-bold text-gray-300 font-cairo mb-3">يحتاج انتباهك</h2>
        {allClear ? (
          <div className="flex items-center gap-3 bg-gray-900 border border-gray-800 rounded-xl p-4">
            <PartyPopper size={20} className="text-green-400" />
            <p className="text-sm text-gray-300 font-cairo">كل شيء تحت السيطرة — لا توجد مهام بانتظارك الآن.</p>
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {attention.pending_review > 0 && (
              <AttentionCard href="/leads" icon={CheckCircle2} count={attention.pending_review}
                title=" عميل بانتظار موافقتك" cta="راجِعهم ووافق على التواصل" tone="border-gold-primary/30 text-gold-primary" />
            )}
            {attention.unanswered > 0 && (
              <AttentionCard href="/inbox" icon={MessageSquare} count={attention.unanswered}
                title=" محادثة بها رسائل جديدة" cta="افتح صندوق الوارد للرد" tone="border-sky-500/30 text-sky-400" />
            )}
            {attention.disconnected.map((n) => (
              <AttentionCard key={n} href="/instances" icon={WifiOff} count="" title={`الرقم «${n}» غير متصل`}
                cta="أعد الربط لاستئناف الإرسال" tone="border-red-500/30 text-red-400" />
            ))}
          </div>
        )}
      </section>

      {/* Today */}
      <section aria-labelledby="today">
        <h2 id="today" className="text-sm font-bold text-gray-300 font-cairo mb-3">اليوم</h2>
        <div className="grid sm:grid-cols-3 gap-3">
          <Meter icon={Smartphone} label="رسائل واتساب" sent={today.whatsapp_sent} limit={today.whatsapp_limit}
            empty={numbers.length ? 'لا توجد أرقام جاهزة لإرسال الحملات اليوم.' : 'لم يتم ربط أي رقم بعد.'} />
          <Meter icon={Mail} label="رسائل البريد" sent={today.email_sent} limit={today.email_limit}
            empty="لم يتم ربط حساب بريد بعد." />
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="flex items-center gap-2 text-sm text-gray-400 font-cairo"><Clock size={16} /> الإرسال القادم</div>
            <div className="mt-2 text-lg font-bold text-white font-cairo">{cairoTime(today.next_run)}</div>
            <p className="mt-1 text-xs text-gray-500 font-cairo">بتوقيت القاهرة، برسائل متباعدة وبالحدود الآمنة.</p>
          </div>
        </div>
      </section>

      <div className="grid lg:grid-cols-5 gap-6">
        {/* This week's results */}
        <section aria-labelledby="week" className="lg:col-span-3 bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="flex items-baseline justify-between mb-4">
            <h2 id="week" className="text-sm font-bold text-white font-cairo">نتائج آخر 7 أيام</h2>
            {week.contacted > 0 && <span className="text-xs text-gray-400 font-cairo">نسبة الرد {replyRate}%</span>}
          </div>
          {week.contacted || week.replied ? <Funnel week={week} /> : (
            <p className="text-sm text-gray-500 font-cairo py-6 text-center">
              ستظهر النتائج هنا بعد أول دفعة رسائل.
            </p>
          )}
        </section>

        {/* Numbers health */}
        <section aria-labelledby="nums" className="lg:col-span-2 bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 id="nums" className="text-sm font-bold text-white font-cairo">أرقام واتساب</h2>
            <Link href="/instances" className="text-xs text-gold-primary hover:underline font-cairo">إدارة</Link>
          </div>
          {numbers.length === 0 ? (
            <Link href="/instances" className="flex items-center gap-2 text-sm text-gray-400 hover:text-white font-cairo py-4">
              <Send size={16} /> اربط أول رقم واتساب
            </Link>
          ) : (
            <ul className="divide-y divide-gray-800">
              {numbers.map((n) => {
                const s = STATE[n.state]
                return (
                  <li key={n.id} className="py-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm text-white truncate" dir="ltr">{n.phone || n.name}</span>
                      <span className={clsx('text-[11px] px-2 py-0.5 rounded-full border font-cairo shrink-0', s.tone)}>{s.label}</span>
                    </div>
                    <p className="text-xs text-gray-500 font-cairo mt-1">{s.hint(n)}</p>
                  </li>
                )
              })}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}
