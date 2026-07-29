'use client'

// Lightweight i18n: a client context that holds the chosen UI language, flips the document
// direction (RTL/LTR), and exposes a t() lookup over per-language dictionaries. Kept
// dependency-free (no next-intl/routing changes) so it layers onto the existing app.
// Page bodies are migrated to t() incrementally; anything not yet keyed falls back to its
// Arabic literal, so the app is never broken mid-migration.
import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from 'react'
import { onboardingApi } from '@/lib/api'

export type UiLang = 'ar' | 'en'
export type AiLang = 'ar' | 'en' | 'masri'

const STORAGE_KEY = 'qualifay_ui_lang'

// Shared-shell strings. Add keys as pages are migrated. Missing key → the fallback passed
// to t(), so partial coverage is safe.
const DICT: Record<UiLang, Record<string, string>> = {
  ar: {
    'settings.title': 'الإعدادات',
    'settings.account': 'معلومات الحساب',
    'settings.name': 'الاسم',
    'settings.email': 'البريد الإلكتروني',
    'settings.project': 'اسم المشروع',
    'settings.save': 'حفظ التغييرات',
    'settings.plan': 'الخطة الحالية',
    'settings.upgrade': 'ترقية الخطة ←',
    'lang.title': 'اللغة',
    'lang.desc': 'اختر لغة واجهة النظام واللغة التي يكتب بها الذكاء الاصطناعي رسائله.',
    'lang.ui': 'لغة الواجهة',
    'lang.ai': 'لغة رسائل الذكاء الاصطناعي',
    'lang.ar': 'العربية (فصحى)',
    'lang.en': 'English',
    'lang.masri': 'مصرية عامية',
    'lang.saved': 'تم حفظ اللغة',
    'lang.save': 'حفظ اللغة',
  },
  en: {
    'settings.title': 'Settings',
    'settings.account': 'Account info',
    'settings.name': 'Name',
    'settings.email': 'Email',
    'settings.project': 'Company name',
    'settings.save': 'Save changes',
    'settings.plan': 'Current plan',
    'settings.upgrade': 'Upgrade plan →',
    'lang.title': 'Language',
    'lang.desc': 'Choose the system UI language and the language the AI writes its messages in.',
    'lang.ui': 'Interface language',
    'lang.ai': 'AI message language',
    'lang.ar': 'Arabic (formal)',
    'lang.en': 'English',
    'lang.masri': 'Egyptian colloquial',
    'lang.saved': 'Language saved',
    'lang.save': 'Save language',
  },
}

interface LangCtx {
  lang: UiLang
  aiLang: AiLang
  dir: 'rtl' | 'ltr'
  setLang: (ui: UiLang, ai: AiLang) => void
  t: (key: string, fallback?: string) => string
}

const Ctx = createContext<LangCtx | null>(null)

function applyDir(lang: UiLang) {
  if (typeof document === 'undefined') return
  document.documentElement.lang = lang
  document.documentElement.dir = lang === 'en' ? 'ltr' : 'rtl'
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<UiLang>('ar')
  const [aiLang, setAiLangState] = useState<AiLang>('ar')

  // 1) instant paint from localStorage, 2) reconcile with the server's saved choice.
  useEffect(() => {
    const cached = (typeof localStorage !== 'undefined' && localStorage.getItem(STORAGE_KEY)) as UiLang | null
    if (cached === 'ar' || cached === 'en') { setLangState(cached); applyDir(cached) }
    else applyDir('ar')
    onboardingApi.getLanguage()
      .then((r) => {
        const ui = (r.data?.ui_language === 'en' ? 'en' : 'ar') as UiLang
        const ai = (['ar', 'en', 'masri'].includes(r.data?.ai_language) ? r.data.ai_language : 'ar') as AiLang
        setLangState(ui); setAiLangState(ai); applyDir(ui)
        try { localStorage.setItem(STORAGE_KEY, ui) } catch {}
      })
      .catch(() => {})
  }, [])

  const setLang = useCallback((ui: UiLang, ai: AiLang) => {
    setLangState(ui); setAiLangState(ai); applyDir(ui)
    try { localStorage.setItem(STORAGE_KEY, ui) } catch {}
  }, [])

  const t = useCallback((key: string, fallback?: string) => DICT[lang][key] ?? fallback ?? key, [lang])

  return (
    <Ctx.Provider value={{ lang, aiLang, dir: lang === 'en' ? 'ltr' : 'rtl', setLang, t }}>
      {children}
    </Ctx.Provider>
  )
}

export function useLang(): LangCtx {
  const c = useContext(Ctx)
  if (!c) return { lang: 'ar', aiLang: 'ar', dir: 'rtl', setLang: () => {}, t: (_k, f) => f ?? _k }
  return c
}
