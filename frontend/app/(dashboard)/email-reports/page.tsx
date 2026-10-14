'use client'

import { useState } from 'react'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import {
  Send, MailOpen, MailX, Reply, UserMinus, Search, Info, ChevronLeft, ChevronRight, Eye,
} from 'lucide-react'
import { emailApi, authApi } from '@/lib/api'

interface Analytics {
  days: number
  totals: { sent: number; delivered: number; opened: number; bounced: number; replied: number; unsubscribed: number; tracked: number }
  rates: { open: number; bounce: number; reply: number; unsubscribe: number }
  series: { day: string; sent: number; opened: number; bounced: number; replied: number; unsubscribed: number }[]
  tracking_enabled: boolean
}

interface SendRow {
  id: string; lead_id: string | null; company: string | null; name: string | null
  to_email: string; subject: string | null; source: string; tracked: boolean
  sent_at: string; opened_at: string | null; open_count: number
  bounced_at: string | null; replied_at: string | null; unsubscribed_at: string | null
}

const RANGES = [7, 30, 90] as const
const FILTERS = [
  { key: '', label: 'الكل' },
  { key: 'opened', label: 'فُتحت' },
  { key: 'not_opened', label: 'لم تُفتح' },
  { key: 'replied', label: 'تم الرد' },
  { key: 'bounced', label: 'مرتدة' },
  { key: 'unsubscribed', label: 'ألغوا الاشتراك' },
] as const

const PAGE_SIZE = 25

function fmtDate(iso: string | null, withTime = true) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('ar-EG', {
      day: 'numeric', month: 'short', ...(withTime ? { hour: 'numeric', minute: '2-digit' } : {}),
      timeZone: 'Africa/Cairo',
    })
  } catch { return '' }
}

function Stat({ icon: I, label, value, rate, hint, tone }: {
  icon: React.ComponentType<{ size?: number; className?: string }>
  label: string; value: number; rate?: string; hint?: string; tone?: string
}) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 text-xs text-gray-400 font-cairo">
        <I size={14} className={tone || 'text-gray-400'} /> {label}
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="text-2xl font-bold text-white tracking-tight">{value.toLocaleString('en')}</span>
        {rate && <span className="text-sm font-semibold text-gray-300">{rate}</span>}
      </div>
      {hint && <p className="mt-1 text-[11px] text-gray-500 font-cairo">{hint}</p>}
    </div>
  )
}

/** Outcome chips for one email. Status always carries an icon + word, never colour alone. */
function Outcome({ r }: { r: SendRow }) {
  const chips: { label: string; icon: React.ReactNode; cls: string }[] = []
  if (r.bounced_at) chips.push({ label: 'مرتدة', icon: <MailX size={12} />, cls: 'text-red-400 bg-red-500/10 border-red-500/30' })
  if (r.unsubscribed_at) chips.push({ label: 'ألغى الاشتراك', icon: <UserMinus size={12} />, cls: 'text-amber-400 bg-amber-500/10 border-amber-500/30' })
  if (r.replied_at) chips.push({ label: 'ردّ', icon: <Reply size={12} />, cls: 'text-green-400 bg-green-500/10 border-green-500/30' })
  if (r.opened_at) chips.push({
    label: r.open_count > 1 ? `فُتحت ×${r.open_count}` : 'فُتحت', icon: <Eye size={12} />,
    cls: 'text-sky-400 bg-sky-500/10 border-sky-500/30',
  })
  if (!chips.length) {
    return <span className="text-xs text-gray-500 font-cairo">{r.tracked ? 'لم تُفتح بعد' : 'أُرسلت (بدون تتبع فتح)'}</span>
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {chips.map((c) => (
        <span key={c.label} className={clsx('inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border font-cairo whitespace-nowrap', c.cls)}>
          {c.icon}{c.label}
        </span>
      ))}
    </div>
  )
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: { payload: Analytics['series'][number] }[] }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  const rows: [string, number][] = [['أُرسلت', d.sent], ['فُتحت', d.opened], ['ردود', d.replied], ['مرتدة', d.bounced], ['ألغوا الاشتراك', d.unsubscribed]]
  return (
    <div className="card px-3 py-2 text-xs font-cairo shadow-raised">
      <div className="font-semibold text-white mb-1">{fmtDate(d.day + 'T12:00:00Z', false)}</div>
      {rows.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-6 text-gray-400"><span>{k}</span><span className="text-white tabular-nums">{v}</span></div>
      ))}
    </div>
  )
}

export default function EmailReportsPage() {
  const [days, setDays] = useState<number>(30)
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [saving, setSaving] = useState(false)

  const { data: me } = useSWR('/auth/me', () => authApi.me().then((r) => r.data))
  const { data, mutate } = useSWR<Analytics>(['email-analytics', days],
    () => emailApi.analytics(days).then((r) => r.data), { refreshInterval: 60000 })
  const { data: list, isLoading: listLoading } = useSWR<{ total: number; items: SendRow[] }>(
    ['email-sends', days, status, search, page],
    () => emailApi.sends({ days, status: status || undefined, search: search || undefined, page, page_size: PAGE_SIZE }).then((r) => r.data),
    { keepPreviousData: true },
  )

  const t = data?.totals
  const pages = list ? Math.max(1, Math.ceil(list.total / PAGE_SIZE)) : 1

  async function toggleTracking() {
    if (!data) return
    setSaving(true)
    try {
      await emailApi.setTracking(!data.tracking_enabled)
      await mutate()
      toast.success(!data.tracking_enabled ? 'تم تفعيل تتبع الفتح' : 'تم إيقاف تتبع الفتح')
    } catch {
      toast.error('تعذّر حفظ الإعداد')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-white font-cairo tracking-tight">تقارير البريد</h1>
          <p className="text-sm text-gray-400 font-cairo mt-1">الرسائل المرسلة للعملاء، ومن فتحها أو ردّ عليها، وما ارتدّ أو أُلغي اشتراكه.</p>
        </div>
        <div className="flex gap-1 bg-gray-900 border border-gray-800 rounded-xl p-1 shadow-card" role="tablist" aria-label="الفترة">
          {RANGES.map((r) => (
            <button key={r} role="tab" aria-selected={days === r} onClick={() => { setDays(r); setPage(1) }}
              className={clsx('px-3 py-1.5 rounded-lg text-sm font-cairo whitespace-nowrap transition-colors',
                days === r ? 'bg-gold-primary text-gray-950 font-semibold' : 'text-gray-400 hover:text-white')}>
              آخر {r} يوم
            </button>
          ))}
        </div>
      </header>

      {/* Totals */}
      <section aria-label="الإجماليات" className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        {!t ? [0, 1, 2, 3, 4].map((i) => <div key={i} className="card h-24 animate-pulse" />) : (
          <>
            <Stat icon={Send} label="أُرسلت" value={t.sent} hint={`${t.delivered} وصلت`} />
            <Stat icon={MailOpen} label="فُتحت" value={t.opened} rate={`${data!.rates.open}%`} tone="text-sky-400"
              hint={t.tracked ? 'من الرسائل المتتبَّعة التي وصلت' : 'تتبع الفتح متوقف'} />
            <Stat icon={Reply} label="ردود" value={t.replied} rate={`${data!.rates.reply}%`} tone="text-green-400" hint="من الرسائل التي وصلت" />
            <Stat icon={MailX} label="مرتدة" value={t.bounced} rate={`${data!.rates.bounce}%`} tone="text-red-400" hint="عناوين غير صالحة — توقف الإرسال لها" />
            <Stat icon={UserMinus} label="ألغوا الاشتراك" value={t.unsubscribed} rate={`${data!.rates.unsubscribe}%`} tone="text-amber-400" hint="لن يُراسَلوا مرة أخرى" />
          </>
        )}
      </section>

      {/* Per day */}
      <section className="card p-4 sm:p-5" aria-labelledby="perday">
        <div className="flex items-baseline justify-between gap-2 mb-4">
          <h2 id="perday" className="text-sm font-bold text-white font-cairo">الرسائل المرسلة يومياً</h2>
          <span className="text-xs text-gray-500 font-cairo">مرّر على عمود لرؤية النتائج</span>
        </div>
        {!data ? <div className="h-56 animate-pulse rounded-xl bg-gray-800/50" /> : data.series.length === 0 ? (
          <p className="h-40 flex items-center justify-center text-sm text-gray-500 font-cairo text-center">
            لم تُرسل أي رسائل بريد في هذه الفترة.
          </p>
        ) : (
          <div className="h-56" dir="ltr">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.series} margin={{ top: 8, right: 4, left: 0, bottom: 0 }} barCategoryGap={2}>
                <CartesianGrid vertical={false} stroke="rgb(var(--c-gray-800))" />
                <XAxis dataKey="day" tickLine={false} axisLine={false} minTickGap={16}
                  tick={{ fill: 'rgb(var(--c-gray-400))', fontSize: 11 }}
                  tickFormatter={(d: string) => d.slice(5).replace('-', '/')} />
                <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={32}
                  tick={{ fill: 'rgb(var(--c-gray-400))', fontSize: 11 }} />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgb(var(--c-gray-800) / 0.6)' }} />
                <Bar dataKey="sent" name="أُرسلت" fill="rgb(var(--c-accent))" radius={[4, 4, 0, 0]} maxBarSize={28} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      {/* Open tracking */}
      {data && (
        <section className="card p-4 flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
          <div className="flex items-start gap-3">
            <Info size={16} className="text-gray-400 shrink-0 mt-0.5" />
            <p className="text-xs text-gray-400 font-cairo leading-relaxed">
              <span className="text-white font-semibold">تتبع الفتح {data.tracking_enabled ? 'مفعّل' : 'متوقف'}.</span>{' '}
              يُحسب الفتح بصورة غير مرئية داخل الرسالة، لذا هو تقديري: بعض برامج البريد تحجب الصور (فتح لا يُحسب)
              وبعضها يحمّلها تلقائياً (فتح يُحسب دون قراءة). الردود والارتدادات وإلغاء الاشتراك دقيقة دائماً.
            </p>
          </div>
          {me?.is_tenant_admin && (
            <button onClick={toggleTracking} disabled={saving} role="switch" aria-checked={data.tracking_enabled}
              className="shrink-0 inline-flex items-center gap-2 text-sm font-cairo px-3 py-2 rounded-xl border border-gray-700 hover:border-gray-600 disabled:opacity-50">
              <span className={clsx('relative w-9 h-5 rounded-full transition-colors', data.tracking_enabled ? 'bg-gold-primary' : 'bg-gray-700')}>
                <span className={clsx('absolute top-0.5 w-4 h-4 rounded-full bg-gray-950 transition-all', data.tracking_enabled ? 'start-[1.125rem]' : 'start-0.5')} />
              </span>
              {data.tracking_enabled ? 'إيقاف التتبع' : 'تفعيل التتبع'}
            </button>
          )}
        </section>
      )}

      {/* Individual emails */}
      <section className="space-y-3" aria-labelledby="sends">
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
          <h2 id="sends" className="text-sm font-bold text-white font-cairo">الرسائل {list ? `(${list.total})` : ''}</h2>
          <div className="relative sm:w-72">
            <Search size={15} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }}
              placeholder="بحث بالشركة أو البريد أو العنوان…"
              className="w-full bg-gray-900 border border-gray-800 rounded-xl pr-9 pl-3 py-2 text-sm text-white placeholder-gray-500 font-cairo" />
          </div>
        </div>

        <div className="scroll-strip" role="tablist" aria-label="تصفية حسب النتيجة">
          {FILTERS.map((f) => (
            <button key={f.key} role="tab" aria-selected={status === f.key} onClick={() => { setStatus(f.key); setPage(1) }}
              className={clsx('shrink-0 px-3 py-1.5 rounded-full text-xs font-cairo border whitespace-nowrap transition-colors',
                status === f.key ? 'bg-gold-primary text-gray-950 border-gold-primary font-semibold' : 'border-gray-800 text-gray-400 hover:text-white hover:border-gray-700')}>
              {f.label}
            </button>
          ))}
        </div>

        <div className="card overflow-hidden">
          {listLoading && !list ? (
            <div className="p-8 flex justify-center"><div className="w-7 h-7 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" /></div>
          ) : !list?.items.length ? (
            <p className="p-10 text-center text-sm text-gray-500 font-cairo">لا توجد رسائل تطابق هذا الاختيار.</p>
          ) : (
            <>
              {/* Phones: stacked cards */}
              <ul className="sm:hidden divide-y divide-gray-800">
                {list.items.map((r) => (
                  <li key={r.id} className="p-4 space-y-1.5">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm font-semibold text-white font-cairo truncate">{r.company || r.name || r.to_email}</span>
                      <span className="text-[11px] text-gray-500 shrink-0">{fmtDate(r.sent_at)}</span>
                    </div>
                    <div className="text-xs text-gray-400 truncate" dir="ltr">{r.to_email}</div>
                    {r.subject && <div className="text-xs text-gray-500 font-cairo truncate">{r.subject}</div>}
                    <Outcome r={r} />
                  </li>
                ))}
              </ul>
              {/* Tablet / desktop: table */}
              <div className="hidden sm:block table-wrap">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-start">
                      <th className="px-4 py-2.5 text-start">العميل</th>
                      <th className="px-4 py-2.5 text-start">العنوان</th>
                      <th className="px-4 py-2.5 text-start">أُرسلت</th>
                      <th className="px-4 py-2.5 text-start">النتيجة</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {list.items.map((r) => (
                      <tr key={r.id}>
                        <td className="px-4 py-3 max-w-[16rem]">
                          <div className="text-white font-cairo truncate">{r.company || r.name || '—'}</div>
                          <div className="text-xs text-gray-500 truncate" dir="ltr">{r.to_email}</div>
                        </td>
                        <td className="px-4 py-3 max-w-[18rem]">
                          <div className="text-gray-300 font-cairo truncate">{r.subject || '—'}</div>
                          <div className="text-[11px] text-gray-500 font-cairo">{r.source === 'sequence' ? 'رسالة متابعة' : 'أول تواصل'}</div>
                        </td>
                        <td className="px-4 py-3 text-xs text-gray-400 whitespace-nowrap">{fmtDate(r.sent_at)}</td>
                        <td className="px-4 py-3"><Outcome r={r} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>

        {list && pages > 1 && (
          <nav className="flex items-center justify-center gap-3 text-sm font-cairo" aria-label="الصفحات">
            <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} aria-label="السابق"
              className="p-2 rounded-lg border border-gray-800 text-gray-400 hover:text-white disabled:opacity-40"><ChevronRight size={16} className="ltr:rotate-180" /></button>
            <span className="text-gray-400">صفحة {page} من {pages}</span>
            <button onClick={() => setPage((p) => Math.min(pages, p + 1))} disabled={page >= pages} aria-label="التالي"
              className="p-2 rounded-lg border border-gray-800 text-gray-400 hover:text-white disabled:opacity-40"><ChevronLeft size={16} className="ltr:rotate-180" /></button>
          </nav>
        )}
      </section>
    </div>
  )
}
