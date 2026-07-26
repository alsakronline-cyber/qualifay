'use client'

import { useState } from 'react'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { Building2, Ban, Play, CalendarPlus, Users, UserRound, LogIn } from 'lucide-react'
import { adminApi } from '@/lib/api'

interface Tenant {
  id: string; name: string; slug: string; plan: string; status: string
  autonomy: string; onboarding_done: boolean; trial_ends_at: string | null
  created_at: string | null; users: number; leads: number
}

const PLANS = ['trial', 'starter', 'growth', 'agency']

function daysLeft(iso: string | null): string {
  if (!iso) return '—'
  const d = Math.ceil((new Date(iso).getTime() - Date.now()) / 86400000)
  return d < 0 ? `منتهية (${-d}ي)` : `${d} يوم`
}

export default function AdminCompaniesPage() {
  const { data, mutate, isLoading } = useSWR('admin-tenants', () => adminApi.tenants().then((r) => r.data))
  const tenants: Tenant[] = Array.isArray(data) ? data : []
  const [busy, setBusy] = useState<string | null>(null)

  async function act(id: string, body: Record<string, unknown>, ok: string) {
    setBusy(id)
    try { await adminApi.updateTenant(id, body); toast.success(ok); await mutate() }
    catch (e: unknown) { toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'فشل') }
    finally { setBusy(null) }
  }

  async function impersonate(t: Tenant) {
    if (!confirm(`الدخول كـ «${t.name}»؟ ستتصفّح كمدير هذه الشركة.`)) return
    setBusy(t.id)
    try {
      const r = await adminApi.impersonate(t.id)
      localStorage.setItem('owner_token', localStorage.getItem('auth_token') || '')
      localStorage.setItem('auth_token', r.data.access_token)
      localStorage.setItem('imp_company', r.data.company)
      window.location.href = '/'   // full reload → app runs as the tenant admin
    } catch (e: unknown) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'تعذّر الدخول')
      setBusy(null)
    }
  }

  return (
    <div className="space-y-5 max-w-5xl">
      <div className="flex items-center gap-2">
        <Building2 size={20} className="text-gold-primary" />
        <div>
          <h1 className="text-2xl font-bold text-white font-cairo">الشركات</h1>
          <p className="text-gray-400 text-sm font-cairo">{tenants.length} شركة على المنصة</p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" /></div>
      ) : (
        <div className="space-y-3">
          {tenants.map((t) => {
            const suspended = t.status === 'suspended'
            return (
              <div key={t.id} className={clsx('bg-gray-900 border rounded-xl p-4', suspended ? 'border-red-500/40' : 'border-gray-800')}>
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-white font-semibold font-cairo">{t.name}</span>
                      {suspended && <span className="text-[10px] bg-red-500/20 text-red-300 rounded-full px-2 py-0.5 font-cairo">موقوفة</span>}
                      {!t.onboarding_done && <span className="text-[10px] bg-gray-700 text-gray-400 rounded-full px-2 py-0.5 font-cairo">لم يكمل الإعداد</span>}
                    </div>
                    <div className="text-xs text-gray-500 mt-0.5" dir="ltr">/{t.slug}</div>
                    <div className="flex items-center gap-3 text-xs text-gray-400 mt-1.5 font-cairo">
                      <span className="flex items-center gap-1"><UserRound size={12} /> {t.users}</span>
                      <span className="flex items-center gap-1"><Users size={12} /> {t.leads} عميل</span>
                      <span>التجربة: {daysLeft(t.trial_ends_at)}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap justify-end">
                    <select
                      value={t.plan} disabled={busy === t.id}
                      onChange={(e) => act(t.id, { plan: e.target.value }, 'تم تغيير الخطة')}
                      className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-white font-cairo focus:outline-none focus:ring-1 focus:ring-gold-primary">
                      {PLANS.map((p) => <option key={p} value={p}>{p}</option>)}
                    </select>
                    <button onClick={() => act(t.id, { extend_trial_days: 30 }, 'تم تمديد التجربة 30 يوم')} disabled={busy === t.id}
                      className="flex items-center gap-1 text-xs bg-gray-800 border border-gray-700 hover:border-gold-primary/40 text-gray-300 rounded-lg px-2.5 py-1.5 font-cairo">
                      <CalendarPlus size={13} /> +٣٠ يوم
                    </button>
                    <button onClick={() => impersonate(t)} disabled={busy === t.id} title="الدخول كهذه الشركة"
                      className="flex items-center gap-1 text-xs bg-gray-800 border border-gray-700 hover:border-gold-primary/40 text-gray-300 rounded-lg px-2.5 py-1.5 font-cairo">
                      <LogIn size={13} /> دخول
                    </button>
                    {suspended ? (
                      <button onClick={() => act(t.id, { status: 'active' }, 'تم تفعيل الشركة')} disabled={busy === t.id}
                        className="flex items-center gap-1 text-xs bg-green-500/10 border border-green-500/30 text-green-400 rounded-lg px-2.5 py-1.5 font-cairo">
                        <Play size={13} /> تفعيل
                      </button>
                    ) : (
                      <button onClick={() => { if (confirm(`إيقاف «${t.name}»؟ لن يتمكن مستخدموها من الدخول.`)) act(t.id, { status: 'suspended' }, 'تم إيقاف الشركة') }} disabled={busy === t.id}
                        className="flex items-center gap-1 text-xs bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg px-2.5 py-1.5 font-cairo">
                        <Ban size={13} /> إيقاف
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
