'use client'

import { useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'
import {
  Building2,
  Target,
  Smartphone,
  Search,
  CheckCircle,
  ChevronRight,
  ChevronLeft,
  SkipForward,
} from 'lucide-react'
import { scrapeApi, settingsApi } from '@/lib/api'

// ─── Types ────────────────────────────────────────────────────────────────────

interface BusinessProfile {
  business_name: string
  industry: string
  target_market: string
  language: 'ar' | 'en'
}

interface IdealCustomer {
  cities: string[]
  value_proposition: string
  min_bant_score: number
}

interface OnboardingState {
  profile: BusinessProfile
  idealCustomer: IdealCustomer
  waConnected: boolean
  scrapeJobId: string | null
  scrapeLeadsFound: number
}

const INDUSTRIES = [
  { value: 'construction', label: 'البناء والإنشاءات / Construction' },
  { value: 'real_estate', label: 'العقارات / Real Estate' },
  { value: 'manufacturing', label: 'التصنيع / Manufacturing' },
  { value: 'retail', label: 'التجزئة / Retail' },
  { value: 'services', label: 'الخدمات / Services' },
  { value: 'other', label: 'أخرى / Other' },
]

const MARKETS = [
  { value: 'small', label: 'شركات صغيرة (1-50) / Small (1-50)' },
  { value: 'medium', label: 'شركات متوسطة (50-200) / Medium (50-200)' },
  { value: 'enterprise', label: 'شركات كبيرة (200+) / Enterprise (200+)' },
  { value: 'all', label: 'الكل / All' },
]

const CITIES = [
  'القاهرة / Cairo',
  'الإسكندرية / Alexandria',
  'الجيزة / Giza',
  'المنصورة / Mansoura',
  'أخرى / Other',
]

const CITY_VALUES = ['Cairo', 'Alexandria', 'Giza', 'Mansoura', 'Other']

const STEPS = [
  { icon: Building2,   label: 'ملف الأعمال',    labelEn: 'Business Profile' },
  { icon: Target,      label: 'العميل المثالي',  labelEn: 'Ideal Customer' },
  { icon: Smartphone,  label: 'واتساب',          labelEn: 'WhatsApp' },
  { icon: Search,      label: 'أول بحث',         labelEn: 'First Scrape' },
  { icon: CheckCircle, label: 'تم!',             labelEn: 'Done!' },
]

// ─── Main wizard ──────────────────────────────────────────────────────────────

export default function OnboardingWizard() {
  const router = useRouter()
  const [step, setStep] = useState(0)
  const [state, setState] = useState<OnboardingState>({
    profile: { business_name: '', industry: '', target_market: '', language: 'ar' },
    idealCustomer: { cities: [], value_proposition: '', min_bant_score: 50 },
    waConnected: false,
    scrapeJobId: null,
    scrapeLeadsFound: 0,
  })
  const [scraping, setScraping] = useState(false)
  const [scrapeQuery, setScrapeQuery] = useState('')
  const [scrapeCity, setScrapeCity] = useState('')

  const updateProfile = (field: keyof BusinessProfile, value: string) =>
    setState((s) => ({ ...s, profile: { ...s.profile, [field]: value } }))

  const updateIdeal = (field: keyof IdealCustomer, value: unknown) =>
    setState((s) => ({ ...s, idealCustomer: { ...s.idealCustomer, [field]: value } }))

  const toggleCity = (city: string) => {
    const current = state.idealCustomer.cities
    const updated = current.includes(city)
      ? current.filter((c) => c !== city)
      : [...current, city]
    updateIdeal('cities', updated)
  }

  const handleSaveProfile = useCallback(async () => {
    try {
      await settingsApi.updateProfile({
        business_name: state.profile.business_name,
        industry: state.profile.industry,
        target_market: state.profile.target_market,
        language: state.profile.language,
        target_cities: state.idealCustomer.cities,
        value_proposition: state.idealCustomer.value_proposition,
        min_approval_score: state.idealCustomer.min_bant_score,
      })
    } catch {
      // Backend might not have this endpoint yet — store in localStorage
      localStorage.setItem('qualifay_onboarding_profile', JSON.stringify({
        ...state.profile,
        ...state.idealCustomer,
      }))
    }
  }, [state.profile, state.idealCustomer])

  const handleStartScrape = useCallback(async () => {
    if (!scrapeQuery) return
    setScraping(true)
    try {
      const res = await scrapeApi.start({
        source: 'google_maps',
        query: scrapeQuery,
        location: scrapeCity || state.idealCustomer.cities[0] || 'Cairo',
        industry: state.profile.industry,
        max_results: 10,
      })
      const jobId = res.data?.job_id || res.data?.id
      setState((s) => ({ ...s, scrapeJobId: jobId, scrapeLeadsFound: 0 }))
      // Poll briefly for lead count
      let found = 0
      for (let i = 0; i < 6; i++) {
        await new Promise((r) => setTimeout(r, 3000))
        try {
          const job = await scrapeApi.get(jobId)
          found = job.data?.leads_found || 0
          setState((s) => ({ ...s, scrapeLeadsFound: found }))
          if (job.data?.status === 'completed') break
        } catch { break }
      }
    } catch {
      toast.error('فشل بدء البحث')
    } finally {
      setScraping(false)
    }
  }, [scrapeQuery, scrapeCity, state.idealCustomer.cities, state.profile.industry])

  const handleFinish = useCallback(() => {
    localStorage.setItem('qualifay_onboarding_done', 'true')
    router.push('/leads')
  }, [router])

  const handleGoToDashboard = useCallback(() => {
    localStorage.setItem('qualifay_onboarding_done', 'true')
    router.push('/')
  }, [router])

  const canProceedStep0 = state.profile.business_name && state.profile.industry
  const canProceedStep1 = state.idealCustomer.value_proposition.length > 0

  const handleNext = useCallback(async () => {
    if (step === 1) {
      // Save profile before moving to step 2
      await handleSaveProfile()
    }
    setStep((s) => s + 1)
  }, [step, handleSaveProfile])

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-xl">
        {/* Step indicator */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {STEPS.map((s, i) => {
            const Icon = s.icon
            const isActive = i === step
            const isDone = i < step
            return (
              <div key={i} className="flex items-center gap-2">
                <div className={clsx(
                  'w-8 h-8 rounded-full flex items-center justify-center transition-all',
                  isDone ? 'bg-green-500 text-white' :
                  isActive ? 'bg-gold-primary text-gray-950' :
                  'bg-gray-800 text-gray-600'
                )}>
                  {isDone ? <CheckCircle size={14} /> : <Icon size={14} />}
                </div>
                {i < STEPS.length - 1 && (
                  <div className={clsx('h-px w-8 transition-all', isDone ? 'bg-green-500' : 'bg-gray-800')} />
                )}
              </div>
            )
          })}
        </div>

        {/* Card */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-5">

          {/* Step 0 — Business Profile */}
          {step === 0 && (
            <div className="space-y-4">
              <div>
                <h2 className="text-xl font-bold text-white font-cairo">مرحباً بك في Qualifay! 👋</h2>
                <p className="text-gray-400 text-sm mt-1">أخبرنا عن عملك · Tell us about your business</p>
              </div>
              <div>
                <label className="block text-xs text-gray-400 font-cairo mb-1.5">اسم الشركة / Business Name</label>
                <input
                  type="text"
                  dir="rtl"
                  value={state.profile.business_name}
                  onChange={(e) => updateProfile('business_name', e.target.value)}
                  placeholder="مثال: شركة النور للمقاولات"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 font-cairo mb-1.5">المجال / Industry</label>
                <select
                  value={state.profile.industry}
                  onChange={(e) => updateProfile('industry', e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo"
                >
                  <option value="">اختر المجال...</option>
                  {INDUSTRIES.map((i) => <option key={i.value} value={i.value}>{i.label}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-400 font-cairo mb-1.5">السوق المستهدف / Target Market</label>
                <select
                  value={state.profile.target_market}
                  onChange={(e) => updateProfile('target_market', e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo"
                >
                  <option value="">اختر...</option>
                  {MARKETS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-400 font-cairo mb-2">اللغة الأساسية / Primary Language</label>
                <div className="flex gap-2">
                  {(['ar', 'en'] as const).map((lang) => (
                    <button
                      key={lang}
                      onClick={() => updateProfile('language', lang)}
                      className={clsx(
                        'flex-1 py-2 rounded-lg text-sm border font-semibold transition-all',
                        state.profile.language === lang
                          ? 'bg-gold-primary text-gray-950 border-gold-primary'
                          : 'bg-gray-800 text-gray-400 border-gray-700 hover:border-gray-600'
                      )}
                    >
                      {lang === 'ar' ? 'العربية' : 'English'}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Step 1 — Ideal Customer */}
          {step === 1 && (
            <div className="space-y-4">
              <div>
                <h2 className="text-xl font-bold text-white font-cairo">العميل المثالي</h2>
                <p className="text-gray-400 text-sm mt-1">من تحاول الوصول إليه؟ · Who are you trying to reach?</p>
              </div>
              <div>
                <label className="block text-xs text-gray-400 font-cairo mb-2">المدن المستهدفة / Target Cities</label>
                <div className="flex flex-wrap gap-2">
                  {CITIES.map((c, i) => {
                    const val = CITY_VALUES[i]
                    return (
                      <button
                        key={val}
                        onClick={() => toggleCity(val)}
                        className={clsx(
                          'px-3 py-1.5 rounded-lg text-xs border transition-all font-cairo',
                          state.idealCustomer.cities.includes(val)
                            ? 'bg-gold-primary/20 text-gold-primary border-gold-primary/40'
                            : 'bg-gray-800 text-gray-400 border-gray-700 hover:border-gray-600'
                        )}
                      >
                        {c}
                      </button>
                    )
                  })}
                </div>
              </div>
              <div>
                <label className="block text-xs text-gray-400 font-cairo mb-1.5">
                  ما هو عرض القيمة الرئيسي؟ / Value Proposition
                </label>
                <textarea
                  value={state.idealCustomer.value_proposition}
                  onChange={(e) => updateIdeal('value_proposition', e.target.value)}
                  maxLength={200}
                  rows={3}
                  dir="rtl"
                  placeholder="مثال: نوفر حلول مقاولات بأسعار منافسة وجودة عالية..."
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo resize-none"
                />
                <div className="text-xs text-gray-600 text-left mt-1">
                  {state.idealCustomer.value_proposition.length}/200
                </div>
              </div>
              <div>
                <label className="block text-xs text-gray-400 font-cairo mb-2">
                  أدنى نتيجة BANT لعرض العملاء / Min BANT Score: <span className="text-white font-bold">{state.idealCustomer.min_bant_score}</span>
                </label>
                <input
                  type="range"
                  min={30} max={80} step={5}
                  value={state.idealCustomer.min_bant_score}
                  onChange={(e) => updateIdeal('min_bant_score', Number(e.target.value))}
                  className="w-full accent-gold-primary"
                />
                <div className="flex justify-between text-xs text-gray-600 mt-1">
                  <span>30 (أكثر عملاء)</span>
                  <span>(جودة أعلى) 80</span>
                </div>
              </div>
            </div>
          )}

          {/* Step 2 — Connect WhatsApp */}
          {step === 2 && (
            <div className="space-y-4">
              <div>
                <h2 className="text-xl font-bold text-white font-cairo">ربط واتساب</h2>
                <p className="text-gray-400 text-sm mt-1">Connect your WhatsApp Business number</p>
              </div>
              {state.waConnected ? (
                <div className="flex items-center gap-3 bg-green-500/10 border border-green-500/30 rounded-xl p-4">
                  <CheckCircle size={20} className="text-green-400 shrink-0" />
                  <div>
                    <p className="text-green-400 font-semibold font-cairo text-sm">تم الربط بنجاح!</p>
                    <p className="text-green-300/70 text-xs">WhatsApp connected</p>
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-4 text-center">
                    <Smartphone size={32} className="mx-auto mb-3 text-gray-500" />
                    <p className="text-gray-300 font-cairo text-sm mb-3">
                      اذهب إلى صفحة واتساب لمسح رمز QR وربط رقمك
                    </p>
                    <a
                      href="/instances"
                      target="_blank"
                      className="inline-flex items-center gap-1.5 bg-wa-green hover:opacity-90 text-white font-semibold text-sm px-4 py-2 rounded-lg transition-opacity font-cairo"
                    >
                      <Smartphone size={14} />
                      ربط واتساب
                    </a>
                  </div>
                  <button
                    onClick={() => setState((s) => ({ ...s, waConnected: true }))}
                    className="w-full text-xs text-gray-500 hover:text-gray-300 py-2 transition-colors font-cairo"
                  >
                    تم الربط بالفعل ✓
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Step 3 — First Scrape */}
          {step === 3 && (
            <div className="space-y-4">
              <div>
                <h2 className="text-xl font-bold text-white font-cairo">أول بحث عن عملاء!</h2>
                <p className="text-gray-400 text-sm mt-1">Let's find your first leads</p>
              </div>

              <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl p-3 text-sm text-blue-300 font-cairo">
                المصدر: Google Maps · الحد الأقصى: 10 نتائج
              </div>

              <div>
                <label className="block text-xs text-gray-400 font-cairo mb-1.5">كلمة البحث / Search Query</label>
                <input
                  type="text"
                  dir="rtl"
                  value={scrapeQuery || state.profile.industry}
                  onChange={(e) => setScrapeQuery(e.target.value)}
                  placeholder="مثال: شركات مقاولات, مطاعم, مصانع..."
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 font-cairo mb-1.5">الموقع / Location</label>
                <input
                  type="text"
                  dir="rtl"
                  value={scrapeCity || state.idealCustomer.cities[0] || ''}
                  onChange={(e) => setScrapeCity(e.target.value)}
                  placeholder="القاهرة / Cairo"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo"
                />
              </div>

              {!state.scrapeJobId ? (
                <button
                  onClick={handleStartScrape}
                  disabled={scraping || !scrapeQuery}
                  className="w-full flex items-center justify-center gap-2 bg-gold-primary hover:bg-gold-dark disabled:opacity-40 text-gray-950 font-semibold text-sm py-2.5 rounded-lg transition-colors font-cairo"
                >
                  {scraping ? (
                    <>
                      <span className="w-4 h-4 border-2 border-gray-950 border-t-transparent rounded-full animate-spin" />
                      جاري البحث...
                    </>
                  ) : (
                    <>
                      <Search size={15} />
                      ابدأ البحث ←
                    </>
                  )}
                </button>
              ) : (
                <div className="bg-green-500/10 border border-green-500/30 rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-1">
                    {scraping ? (
                      <span className="w-4 h-4 border-2 border-green-400 border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <CheckCircle size={16} className="text-green-400" />
                    )}
                    <p className="text-green-400 font-cairo text-sm font-semibold">
                      {scraping ? 'جاري البحث...' : 'اكتمل البحث!'}
                    </p>
                  </div>
                  {state.scrapeLeadsFound > 0 && (
                    <p className="text-green-300/80 text-xs font-cairo">
                      تم العثور على {state.scrapeLeadsFound} عميل محتمل حتى الآن
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Step 4 — Done */}
          {step === 4 && (
            <div className="space-y-5 text-center">
              <div>
                <div className="text-5xl mb-3">🎉</div>
                <h2 className="text-xl font-bold text-white font-cairo">أنت جاهز!</h2>
                <p className="text-gray-400 text-sm mt-1">You're all set!</p>
              </div>

              <div className="space-y-2 text-right">
                <div className="flex items-center gap-3 bg-gray-800/50 rounded-xl p-3">
                  <CheckCircle size={16} className="text-green-400 shrink-0" />
                  <span className="text-sm text-gray-200 font-cairo">تم حفظ ملف الأعمال</span>
                </div>
                <div className="flex items-center gap-3 bg-gray-800/50 rounded-xl p-3">
                  {state.waConnected ? (
                    <CheckCircle size={16} className="text-green-400 shrink-0" />
                  ) : (
                    <SkipForward size={16} className="text-gray-500 shrink-0" />
                  )}
                  <span className="text-sm text-gray-200 font-cairo">
                    {state.waConnected ? 'تم ربط واتساب' : 'تم تخطي ربط واتساب'}
                  </span>
                </div>
                <div className="flex items-center gap-3 bg-gray-800/50 rounded-xl p-3">
                  {state.scrapeJobId ? (
                    <CheckCircle size={16} className="text-green-400 shrink-0" />
                  ) : (
                    <SkipForward size={16} className="text-gray-500 shrink-0" />
                  )}
                  <span className="text-sm text-gray-200 font-cairo">
                    {state.scrapeJobId
                      ? `تم بدء البحث · وُجد ${state.scrapeLeadsFound} عميل`
                      : 'تم تخطي البحث الأول'}
                  </span>
                </div>
              </div>

              <div className="flex flex-col gap-2">
                {state.scrapeLeadsFound > 0 && (
                  <button
                    onClick={handleFinish}
                    className="w-full bg-gold-primary hover:bg-gold-dark text-gray-950 font-semibold text-sm py-2.5 rounded-lg transition-colors font-cairo"
                  >
                    مراجعة {state.scrapeLeadsFound} عميل محتمل ←
                  </button>
                )}
                <button
                  onClick={handleGoToDashboard}
                  className={clsx(
                    'w-full text-sm py-2.5 rounded-lg transition-colors font-cairo',
                    state.scrapeLeadsFound > 0
                      ? 'border border-gray-700 text-gray-400 hover:text-white hover:border-gray-600'
                      : 'bg-gold-primary hover:bg-gold-dark text-gray-950 font-semibold'
                  )}
                >
                  الذهاب للوحة التحكم
                </button>
              </div>
            </div>
          )}

          {/* Navigation buttons */}
          {step < 4 && (
            <div className="flex items-center justify-between pt-2 border-t border-gray-800">
              <button
                onClick={() => setStep((s) => s - 1)}
                disabled={step === 0}
                className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white disabled:opacity-30 transition-colors font-cairo"
              >
                <ChevronRight size={15} />
                رجوع
              </button>

              <div className="flex items-center gap-2">
                {/* Skip button for steps 2 and 3 */}
                {(step === 2 || step === 3) && (
                  <button
                    onClick={() => setStep((s) => s + 1)}
                    className="text-xs text-gray-500 hover:text-gray-300 px-3 py-1.5 transition-colors font-cairo"
                  >
                    تخطي
                  </button>
                )}

                <button
                  onClick={step === 3 && state.scrapeJobId ? () => setStep(4) : handleNext}
                  disabled={
                    (step === 0 && !canProceedStep0) ||
                    (step === 1 && !canProceedStep1) ||
                    (step === 3 && scraping)
                  }
                  className="flex items-center gap-1.5 bg-gold-primary hover:bg-gold-dark disabled:opacity-40 text-gray-950 font-semibold text-sm px-4 py-2 rounded-lg transition-colors font-cairo"
                >
                  التالي
                  <ChevronLeft size={15} />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Step label */}
        <p className="text-center text-xs text-gray-600 mt-3 font-cairo">
          {STEPS[step].label} · {STEPS[step].labelEn} · {step + 1}/{STEPS.length}
        </p>
      </div>
    </div>
  )
}
