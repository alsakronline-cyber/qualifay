'use client'

import { useState, useCallback } from 'react'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { formatDistanceToNow } from 'date-fns'
import { ar } from 'date-fns/locale'
import {
  Search, StopCircle, RefreshCw, Map, Globe, BookOpen, Users, Lightbulb, Briefcase,
  Target, Layers, Database, Phone, X, ChevronLeft, ChevronRight, CalendarClock,
  Trash2, Zap,
} from 'lucide-react'
import { scrapeApi } from '@/lib/api'
import type { ScrapeJob } from '@/lib/types'

interface FieldDef { name: string; label: string; type: 'text' | 'number'; placeholder?: string; required?: boolean }
interface SourceConfig {
  source: string
  label: string
  desc: string
  icon: React.ComponentType<{ size?: number; className?: string }>
  color: string
  badge?: string
  fields: FieldDef[]
}

const SOURCES: SourceConfig[] = [
  { source: 'google_maps', label: 'خرائط جوجل', desc: 'شركات محلية بالهاتف والموقع', icon: Map, color: 'text-green-400',
    fields: [
      { name: 'query', label: 'المجال / الكلمة البحثية', type: 'text', placeholder: 'صيدليات، مطاعم، مصانع...', required: true },
      { name: 'location', label: 'المدينة / المنطقة', type: 'text', placeholder: 'القاهرة، الجيزة، الإسكندرية' },
    ] },
  { source: 'apollo', label: 'قاعدة بيانات الشركات', desc: 'OpenStreetMap — مجاني بالكامل', icon: Database, color: 'text-emerald-400', badge: 'مجاني',
    fields: [
      { name: 'query', label: 'نوع النشاط', type: 'text', placeholder: 'مستشفى، فندق، مصنع...', required: true },
      { name: 'location', label: 'المدينة', type: 'text', placeholder: 'القاهرة' },
    ] },
  { source: 'yellowpages', label: 'الصفحات الصفراء', desc: 'دليل الشركات المصري', icon: Phone, color: 'text-yellow-400',
    fields: [
      { name: 'query', label: 'المجال', type: 'text', placeholder: 'بلاستيك، مقاولات، أدوية...', required: true },
      { name: 'location', label: 'المدينة', type: 'text', placeholder: 'القاهرة' },
    ] },
  { source: 'web_scrape', label: 'مواقع الويب', desc: 'استخراج من موقع أو نطاق', icon: Globe, color: 'text-gray-400',
    fields: [
      { name: 'query', label: 'الموقع أو الكلمة البحثية', type: 'text', placeholder: 'https://example.com', required: true },
      { name: 'industry', label: 'المجال', type: 'text', placeholder: 'التصميم' },
    ] },
  { source: 'directories', label: 'الأدلة التجارية', desc: 'أدلة الأعمال الدولية', icon: BookOpen, color: 'text-gray-400',
    fields: [
      { name: 'industry', label: 'المجال', type: 'text', placeholder: 'الاستشارات', required: true },
      { name: 'location', label: 'المدينة', type: 'text', placeholder: 'القاهرة' },
    ] },
  { source: 'linkedin', label: 'LinkedIn', desc: 'عبر بحث جوجل — بدون حظر', icon: Users, color: 'text-gray-400', badge: 'بحث',
    fields: [
      { name: 'query', label: 'المسمى الوظيفي / المجال', type: 'text', placeholder: 'Marketing Manager', required: true },
      { name: 'location', label: 'الدولة / المدينة', type: 'text', placeholder: 'Egypt' },
    ] },
  { source: 'facebook', label: 'مكتبة إعلانات فيسبوك', desc: 'واجهة ميتا الرسمية المجانية', icon: Layers, color: 'text-gray-400', badge: 'API',
    fields: [
      { name: 'query', label: 'الكلمة البحثية / المجال', type: 'text', placeholder: 'شركات مقاولات', required: true },
    ] },
  { source: 'tender', label: 'المناقصات', desc: 'مناقصات ومشاريع حكومية', icon: Briefcase, color: 'text-amber-400',
    fields: [
      { name: 'query', label: 'نوع المناقصة', type: 'text', placeholder: 'مشاريع بناء', required: true },
      { name: 'location', label: 'الجهة', type: 'text', placeholder: 'مصر' },
    ] },
  { source: 'enrichment', label: 'إثراء البيانات', desc: 'استكمال بيانات شركة', icon: Lightbulb, color: 'text-yellow-400',
    fields: [
      { name: 'query', label: 'النطاق أو اسم الشركة', type: 'text', placeholder: 'company.com', required: true },
    ] },
  { source: 'competitor_ads', label: 'إعلانات منافسين', desc: 'تحليل إعلانات المنافسين', icon: Target, color: 'text-gray-400',
    fields: [
      { name: 'query', label: 'اسم المنافس أو المجال', type: 'text', placeholder: 'شركات توصيل', required: true },
    ] },
]

const COUNT_PRESETS = [25, 50, 100, 200]

const JOB_STATUS: Record<string, { label: string; color: string; bg: string }> = {
  pending: { label: 'انتظار', color: 'text-gray-400', bg: 'bg-gray-700/50' },
  running: { label: 'جارٍ', color: 'text-gray-400', bg: 'bg-gray-500/20' },
  done: { label: 'مكتمل', color: 'text-green-400', bg: 'bg-green-500/10' },
  completed: { label: 'مكتمل', color: 'text-green-400', bg: 'bg-green-500/10' },
  paused: { label: 'متوقف مؤقتاً', color: 'text-yellow-400', bg: 'bg-yellow-500/10' },
  error: { label: 'خطأ', color: 'text-red-400', bg: 'bg-red-500/10' },
  cancelled: { label: 'ملغى', color: 'text-gray-500', bg: 'bg-gray-800' },
}
const SOURCE_LABELS: Record<string, string> = Object.fromEntries(SOURCES.map((s) => [s.source, s.label]))

interface Schedule {
  id: string; source: string; config: Record<string, string | number>
  hour_cairo: number; enabled: boolean; monthly_cap: number; monthly_count: number; last_run_at: string | null
}

export default function ScrapePage() {
  const [wizardOpen, setWizardOpen] = useState(false)
  const [step, setStep] = useState(1)
  const [source, setSource] = useState<SourceConfig | null>(null)
  const [form, setForm] = useState<Record<string, string>>({})
  const [count, setCount] = useState(50)
  const [scheduleOn, setScheduleOn] = useState(false)
  const [hour, setHour] = useState(9)
  const [monthlyCap, setMonthlyCap] = useState(1000)
  const [submitting, setSubmitting] = useState(false)

  const { data: jobsData, mutate: mutateJobs } = useSWR('scrape/jobs', () => scrapeApi.list().then((r) => r.data), { refreshInterval: 4000 })
  const { data: schedData, mutate: mutateSched } = useSWR('scrape/schedules', () => scrapeApi.listSchedules().then((r) => r.data), { refreshInterval: 15000 })

  const jobs: ScrapeJob[] = Array.isArray(jobsData) ? jobsData : (jobsData?.items || jobsData?.jobs || [])
  const schedules: Schedule[] = Array.isArray(schedData) ? schedData : []
  const runningCount = jobs.filter((j) => j.status === 'running' || j.status === 'pending').length

  const resetWizard = useCallback(() => {
    setStep(1); setSource(null); setForm({}); setCount(50)
    setScheduleOn(false); setHour(9); setMonthlyCap(1000)
  }, [])

  const closeWizard = useCallback(() => { setWizardOpen(false); resetWizard() }, [resetWizard])

  const canProceed = useCallback(() => {
    if (step === 1) return !!source
    if (step === 2) return source!.fields.filter((f) => f.required).every((f) => form[f.name]?.trim())
    return true
  }, [step, source, form])

  const handleSubmit = useCallback(async () => {
    if (!source) return
    setSubmitting(true)
    try {
      const base: Record<string, unknown> = { source: source.source, max_results: count }
      for (const [k, v] of Object.entries(form)) if (v?.trim()) base[k] = v
      if (scheduleOn) {
        await scrapeApi.createSchedule({ ...base, hour_cairo: hour, monthly_cap: monthlyCap } as Parameters<typeof scrapeApi.createSchedule>[0])
        toast.success('تم تفعيل البحث اليومي التلقائي')
        mutateSched()
      } else {
        await scrapeApi.start(base as Parameters<typeof scrapeApi.start>[0])
        toast.success('بدأ البحث عن العملاء')
      }
      mutateJobs()
      closeWizard()
    } catch {
      toast.error('فشل تنفيذ الطلب')
    } finally {
      setSubmitting(false)
    }
  }, [source, form, count, scheduleOn, hour, monthlyCap, mutateJobs, mutateSched, closeWizard])

  const handleCancel = useCallback(async (id: string) => {
    try { await scrapeApi.cancel(id); mutateJobs() } catch { toast.error('فشل الإلغاء') }
  }, [mutateJobs])

  const removeSchedule = useCallback(async (id: string) => {
    try { await scrapeApi.deleteSchedule(id); mutateSched() } catch { toast.error('فشل الحذف') }
  }, [mutateSched])

  return (
    <div className="space-y-6">
      {/* Hero: Search For Leads */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white font-cairo">جمع العملاء المحتملين</h1>
          <p className="text-gray-400 text-sm mt-1">ابحث عن عملاء جدد من مصادر متعددة، أو فعّل بحثاً يومياً تلقائياً</p>
        </div>
        <button
          onClick={() => { resetWizard(); setWizardOpen(true) }}
          className="flex items-center gap-2 bg-gradient-to-r from-gold-primary to-gold-dark text-gray-950 font-bold px-6 py-3 rounded-xl hover:opacity-90 transition-all font-cairo text-base shadow-lg shadow-gold-primary/20"
        >
          <Search size={20} />
          بحث عن عملاء
        </button>
      </div>

      {/* Active schedules */}
      {schedules.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <h2 className="text-sm font-semibold text-white font-cairo mb-3 flex items-center gap-2">
            <CalendarClock size={16} className="text-gold-primary" /> عمليات البحث اليومية التلقائية
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {schedules.map((s) => (
              <div key={s.id} className="flex items-center justify-between bg-gray-800/50 rounded-lg px-3 py-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-white font-cairo">{SOURCE_LABELS[s.source] || s.source}</span>
                    <span className={clsx('text-[10px] px-1.5 py-0.5 rounded-full font-cairo', s.enabled ? 'bg-green-500/15 text-green-400' : 'bg-gray-700 text-gray-400')}>
                      {s.enabled ? 'مفعّل' : 'موقوف'}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 font-cairo truncate">
                    {String(s.config.query || s.config.industry || '')}{s.config.location ? ` · ${s.config.location}` : ''} · يومياً {s.hour_cairo}:00 · {s.monthly_count}/{s.monthly_cap} هذا الشهر
                  </p>
                </div>
                <button onClick={() => removeSchedule(s.id)} className="text-red-400 hover:text-red-300 p-1.5 shrink-0" title="حذف">
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Jobs list */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-white font-cairo">مهام البحث</h2>
          <div className="flex items-center gap-2">
            {runningCount > 0 && (
              <span className="text-xs bg-gray-500/10 text-gray-400 border border-gray-500/30 px-2 py-0.5 rounded-full font-semibold font-cairo animate-pulse">{runningCount} نشط</span>
            )}
            <button onClick={() => mutateJobs()} className="text-gray-400 hover:text-white p-1.5 rounded-lg hover:bg-gray-800"><RefreshCw size={14} /></button>
          </div>
        </div>
        {jobs.length === 0 ? (
          <div className="text-center py-12 text-gray-600 font-cairo text-sm">
            لا توجد مهام بعد. اضغط «بحث عن عملاء» للبدء.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-[520px] overflow-y-auto pr-1">
            {jobs.map((job) => {
              const cfg = JOB_STATUS[job.status] || JOB_STATUS.pending
              const isActive = job.status === 'running' || job.status === 'pending'
              return (
                <div key={job.id} className="bg-gray-800/50 rounded-lg p-3 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className={clsx('text-xs px-2 py-0.5 rounded font-semibold font-cairo', cfg.bg, cfg.color)}>{cfg.label}</span>
                      <span className="text-sm text-white font-cairo">{SOURCE_LABELS[job.source] || job.source}</span>
                    </div>
                    {isActive && <button onClick={() => handleCancel(job.id)} className="text-red-400 hover:text-red-300 p-1"><StopCircle size={14} /></button>}
                  </div>
                  {job.config && Object.keys(job.config).length > 0 && (
                    <p className="text-xs text-gray-500 font-cairo truncate">
                      {String(job.config.query || job.config.industry || '')}{job.config.location ? ` · ${job.config.location}` : ''}
                    </p>
                  )}
                  {(job.status === 'done' || job.status === 'completed') && (
                    <p className="text-xs font-cairo text-gray-400">وُجد: <span className="text-white font-semibold">{job.leads_found || 0}</span> عميل</p>
                  )}
                  {job.status === 'error' && job.error_message && (
                    <p className="text-xs text-red-400/80 font-cairo truncate" title={job.error_message}>{job.error_message}</p>
                  )}
                  <p className="text-xs text-gray-600 font-cairo">{formatDistanceToNow(new Date(job.created_at), { locale: ar, addSuffix: true })}</p>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Wizard modal */}
      {wizardOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={closeWizard}>
          <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
            {/* Header + steps */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
              <h3 className="text-lg font-bold text-white font-cairo">بحث عن عملاء</h3>
              <button onClick={closeWizard} className="text-gray-400 hover:text-white"><X size={20} /></button>
            </div>
            <div className="flex items-center gap-1 px-6 py-3 border-b border-gray-800">
              {['المصدر', 'التفاصيل', 'العدد', 'الجدولة'].map((lbl, i) => (
                <div key={lbl} className="flex items-center gap-1 flex-1">
                  <div className={clsx('w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0', step > i + 1 ? 'bg-green-500 text-white' : step === i + 1 ? 'bg-gold-primary text-gray-950' : 'bg-gray-700 text-gray-400')}>{i + 1}</div>
                  <span className={clsx('text-xs font-cairo', step === i + 1 ? 'text-white' : 'text-gray-500')}>{lbl}</span>
                  {i < 3 && <div className="h-px flex-1 bg-gray-700 mx-1" />}
                </div>
              ))}
            </div>

            <div className="px-6 py-5 overflow-y-auto flex-1">
              {/* Step 1: source */}
              {step === 1 && (
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {SOURCES.map((s) => {
                    const Icon = s.icon
                    const active = source?.source === s.source
                    return (
                      <button key={s.source} onClick={() => { setSource(s); setForm({}) }}
                        className={clsx('relative flex flex-col items-start gap-1 px-3 py-3 rounded-xl border text-right transition-all',
                          active ? 'bg-gold-primary/10 border-gold-primary/50' : 'bg-gray-800/50 border-gray-700 hover:border-gray-600')}>
                        {s.badge && <span className="absolute top-1.5 left-1.5 text-[9px] bg-gray-500/20 text-gray-300 border border-gray-500/30 rounded px-1 font-mono">{s.badge}</span>}
                        <Icon size={18} className={active ? 'text-gold-primary' : s.color} />
                        <span className="text-xs font-cairo font-medium text-white leading-tight">{s.label}</span>
                        <span className="text-[10px] text-gray-500 font-cairo leading-tight">{s.desc}</span>
                      </button>
                    )
                  })}
                </div>
              )}

              {/* Step 2: fields */}
              {step === 2 && source && (
                <div className="space-y-4">
                  <p className="text-sm text-gray-400 font-cairo">حدّد ما تبحث عنه بدقة للحصول على أفضل النتائج.</p>
                  {source.fields.map((f) => (
                    <div key={f.name}>
                      <label className="block text-sm text-gray-300 font-cairo mb-1.5">{f.label}{f.required && <span className="text-red-400 mr-1">*</span>}</label>
                      <input type="text" placeholder={f.placeholder} value={form[f.name] || ''}
                        onChange={(e) => setForm((p) => ({ ...p, [f.name]: e.target.value }))}
                        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo" />
                    </div>
                  ))}
                </div>
              )}

              {/* Step 3: count */}
              {step === 3 && (
                <div className="space-y-4">
                  <label className="block text-sm text-gray-300 font-cairo">كم عدد العملاء الذين تريد جمعهم؟</label>
                  <div className="grid grid-cols-4 gap-2">
                    {COUNT_PRESETS.map((c) => (
                      <button key={c} onClick={() => setCount(c)}
                        className={clsx('py-3 rounded-lg border font-bold font-cairo transition-all', count === c ? 'bg-gold-primary/10 border-gold-primary text-gold-primary' : 'bg-gray-800/50 border-gray-700 text-gray-400 hover:border-gray-600')}>
                        {c}
                      </button>
                    ))}
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 font-cairo mb-1.5">أو أدخل رقماً مخصصاً (حتى 500)</label>
                    <input type="number" min={1} max={500} value={count}
                      onChange={(e) => setCount(Math.min(500, Math.max(1, Number(e.target.value) || 1)))}
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-white font-cairo" />
                  </div>
                </div>
              )}

              {/* Step 4: schedule */}
              {step === 4 && (
                <div className="space-y-4">
                  <button onClick={() => setScheduleOn((v) => !v)}
                    className={clsx('w-full flex items-center justify-between px-4 py-3 rounded-xl border transition-all', scheduleOn ? 'bg-gold-primary/10 border-gold-primary/50' : 'bg-gray-800/50 border-gray-700')}>
                    <div className="text-right">
                      <div className="flex items-center gap-2"><Zap size={16} className={scheduleOn ? 'text-gold-primary' : 'text-gray-400'} /><span className="text-sm font-cairo font-medium text-white">تشغيل بحث يومي تلقائي</span></div>
                      <p className="text-xs text-gray-500 font-cairo mt-0.5">يعيد النظام تشغيل هذا البحث كل يوم تلقائياً</p>
                    </div>
                    <div className={clsx('w-11 h-6 rounded-full p-0.5 transition-colors', scheduleOn ? 'bg-gold-primary' : 'bg-gray-600')}>
                      <div className={clsx('w-5 h-5 bg-white rounded-full transition-transform', scheduleOn ? 'translate-x-0' : 'translate-x-5')} />
                    </div>
                  </button>

                  {scheduleOn && (
                    <div className="space-y-3 pr-1">
                      <div>
                        <label className="block text-sm text-gray-300 font-cairo mb-1.5">وقت التشغيل يومياً (توقيت القاهرة)</label>
                        <select value={hour} onChange={(e) => setHour(Number(e.target.value))}
                          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-white font-cairo">
                          {Array.from({ length: 24 }).map((_, h) => <option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="block text-sm text-gray-300 font-cairo mb-1.5">الحد الأقصى للعملاء شهرياً</label>
                        <input type="number" min={1} value={monthlyCap} onChange={(e) => setMonthlyCap(Math.max(1, Number(e.target.value) || 1))}
                          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-white font-cairo" />
                        <p className="text-xs text-gray-500 font-cairo mt-1">يتوقف الجمع تلقائياً عند بلوغ هذا الحد، مع تجاهل العملاء المكررين.</p>
                      </div>
                    </div>
                  )}

                  {/* Summary */}
                  <div className="bg-gray-800/50 rounded-lg p-3 text-xs font-cairo text-gray-400 space-y-1">
                    <p>المصدر: <span className="text-white">{source?.label}</span></p>
                    <p>البحث: <span className="text-white">{form.query || form.industry || '—'}{form.location ? ` · ${form.location}` : ''}</span></p>
                    <p>العدد: <span className="text-white">{count}</span>{scheduleOn ? ` · يومياً ${String(hour).padStart(2, '0')}:00` : ' · مرة واحدة الآن'}</p>
                  </div>
                </div>
              )}
            </div>

            {/* Footer nav */}
            <div className="flex items-center justify-between px-6 py-4 border-t border-gray-800">
              <button onClick={() => (step === 1 ? closeWizard() : setStep((s) => s - 1))}
                className="flex items-center gap-1 text-sm text-gray-400 hover:text-white font-cairo px-3 py-2">
                <ChevronRight size={16} />{step === 1 ? 'إلغاء' : 'السابق'}
              </button>
              {step < 4 ? (
                <button onClick={() => canProceed() ? setStep((s) => s + 1) : toast.error('أكمل الحقول المطلوبة')}
                  disabled={!canProceed()}
                  className="flex items-center gap-1 bg-gold-primary text-gray-950 font-bold px-6 py-2 rounded-lg hover:opacity-90 disabled:opacity-40 font-cairo">
                  التالي <ChevronLeft size={16} />
                </button>
              ) : (
                <button onClick={handleSubmit} disabled={submitting}
                  className="flex items-center gap-2 bg-gradient-to-r from-gold-primary to-gold-dark text-gray-950 font-bold px-6 py-2 rounded-lg hover:opacity-90 disabled:opacity-50 font-cairo">
                  {submitting ? <span className="w-4 h-4 border-2 border-gray-950 border-t-transparent rounded-full animate-spin" /> : <Search size={16} />}
                  {scheduleOn ? 'تفعيل البحث اليومي' : 'ابدأ البحث الآن'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
