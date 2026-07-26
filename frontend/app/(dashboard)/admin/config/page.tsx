'use client'

import { useState, useEffect } from 'react'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { SlidersHorizontal, Save } from 'lucide-react'
import { adminApi } from '@/lib/api'

type Limits = Record<string, Record<string, number>>
type Features = Record<string, boolean>
interface Config { plan_limits: Limits; features: Features }

const LIMIT_LABELS: Record<string, string> = { wa_instances: 'أجهزة واتساب', monthly_leads: 'عملاء/شهر' }
const FEATURE_LABELS: Record<string, string> = {
  allow_signups: 'السماح بتسجيل شركات جديدة', scraping: 'جمع البيانات (Scraping)', ai_replies: 'ردود الذكاء الاصطناعي',
}

export default function AdminConfigPage() {
  const { data, mutate } = useSWR('admin-config', () => adminApi.config().then((r) => r.data))
  const [cfg, setCfg] = useState<Config | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => { if (data?.config) setCfg(data.config) }, [data])
  if (!cfg) return <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" /></div>

  const setLimit = (plan: string, key: string, v: number) =>
    setCfg((c) => c && ({ ...c, plan_limits: { ...c.plan_limits, [plan]: { ...c.plan_limits[plan], [key]: v } } }))
  const setFeature = (k: string, v: boolean) =>
    setCfg((c) => c && ({ ...c, features: { ...c.features, [k]: v } }))

  async function save() {
    if (!cfg) return
    setSaving(true)
    try { await adminApi.saveConfig(cfg as unknown as Record<string, unknown>); toast.success('تم الحفظ'); await mutate() }
    catch { toast.error('فشل الحفظ') } finally { setSaving(false) }
  }

  const plans = Object.keys(cfg.plan_limits)
  const limitKeys = Object.keys(LIMIT_LABELS)

  return (
    <div className="space-y-5 max-w-3xl">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <SlidersHorizontal size={20} className="text-gold-primary" />
          <div><h1 className="text-2xl font-bold text-white font-cairo">حدود الخطط والميزات</h1><p className="text-gray-400 text-sm font-cairo">0 = بلا حدود</p></div>
        </div>
        <button onClick={save} disabled={saving} className="flex items-center gap-1.5 bg-gold-primary text-gray-950 font-semibold text-sm px-4 py-2 rounded-lg disabled:opacity-50 font-cairo">
          <Save size={15} /> {saving ? 'جارٍ...' : 'حفظ'}
        </button>
      </div>

      {/* Plan limits table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 font-cairo text-xs">
              <th className="text-right py-2">الخطة</th>
              {limitKeys.map((k) => <th key={k} className="text-center py-2 px-2">{LIMIT_LABELS[k]}</th>)}
            </tr>
          </thead>
          <tbody>
            {plans.map((p) => (
              <tr key={p} className="border-t border-gray-800">
                <td className="py-2 text-white font-cairo capitalize">{p}</td>
                {limitKeys.map((k) => (
                  <td key={k} className="py-2 px-2 text-center">
                    <input type="number" min={0} value={cfg.plan_limits[p]?.[k] ?? 0}
                      onChange={(e) => setLimit(p, k, parseInt(e.target.value) || 0)}
                      className="w-20 bg-gray-800 border border-gray-700 rounded-lg px-2 py-1 text-center text-white focus:outline-none focus:ring-1 focus:ring-gold-primary" />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Feature flags */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-2">
        <h2 className="text-sm font-bold text-white font-cairo mb-2">مفاتيح الميزات</h2>
        {Object.keys(cfg.features).map((k) => (
          <label key={k} className="flex items-center justify-between py-2 border-b border-gray-800 last:border-0">
            <span className="text-sm text-gray-200 font-cairo">{FEATURE_LABELS[k] || k}</span>
            <button onClick={() => setFeature(k, !cfg.features[k])}
              className={clsx('w-11 h-6 rounded-full transition-colors relative', cfg.features[k] ? 'bg-gold-primary' : 'bg-gray-700')}>
              <span className={clsx('absolute top-0.5 w-5 h-5 bg-white rounded-full transition-all', cfg.features[k] ? 'left-0.5' : 'right-0.5')} />
            </button>
          </label>
        ))}
      </div>
    </div>
  )
}
