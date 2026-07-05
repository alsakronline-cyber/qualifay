'use client'

import { clsx } from 'clsx'
import { Check } from 'lucide-react'
import useSWR from 'swr'
import { authApi } from '@/lib/api'
import type { AuthUser } from '@/lib/types'

const PLANS = [
  {
    id: 'trial',
    name: 'Trial',
    nameAr: 'تجريبي',
    price: 'مجاناً',
    priceEn: 'Free',
    features: ['50 عميل محتمل', 'نسخة واتساب واحدة', 'لوحة تحكم أساسية'],
  },
  {
    id: 'starter',
    name: 'Starter',
    nameAr: 'مبتدئ',
    price: '$49/شهر',
    priceEn: '$49/mo',
    features: ['500 عميل محتمل', '3 نسخ واتساب', 'ذكاء اصطناعي BANT', 'دعم بالبريد'],
  },
  {
    id: 'growth',
    name: 'Growth',
    nameAr: 'نمو',
    price: '$149/شهر',
    priceEn: '$149/mo',
    highlight: true,
    features: ['2000 عميل محتمل', '10 نسخ واتساب', 'حملات متقدمة', 'تقارير تفصيلية', 'دعم أولوية'],
  },
  {
    id: 'agency',
    name: 'Agency',
    nameAr: 'وكالة',
    price: '$399/شهر',
    priceEn: '$399/mo',
    features: ['غير محدود', 'نسخ غير محدودة', 'API كامل', 'White-label', 'مدير حساب مخصص'],
  },
]

export default function BillingPage() {
  const { data: user } = useSWR<AuthUser>('auth/me', () => authApi.me().then((r) => r.data))
  const currentPlan = user?.tenant?.plan || 'trial'

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white font-cairo">الفوترة والخطط</h1>
        <p className="text-gray-400 text-sm mt-1">Billing & Plans</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {PLANS.map((plan) => {
          const isCurrent = currentPlan === plan.id
          return (
            <div
              key={plan.id}
              className={clsx(
                'bg-gray-900 border rounded-xl p-5 space-y-4 relative',
                plan.highlight
                  ? 'border-gold-primary/50 ring-1 ring-gold-primary/30'
                  : 'border-gray-800',
                isCurrent && 'border-green-500/40'
              )}
            >
              {plan.highlight && (
                <div className="absolute -top-3 right-1/2 translate-x-1/2">
                  <span className="bg-gold-primary text-gray-950 text-xs font-bold px-3 py-1 rounded-full font-cairo">
                    الأكثر شعبية
                  </span>
                </div>
              )}
              {isCurrent && (
                <div className="absolute -top-3 left-4">
                  <span className="bg-green-500 text-white text-xs font-bold px-3 py-1 rounded-full font-cairo">
                    خطتك الحالية
                  </span>
                </div>
              )}

              <div>
                <h3 className="text-lg font-bold text-white font-cairo">{plan.nameAr}</h3>
                <p className="text-sm text-gray-500">{plan.name}</p>
              </div>

              <div>
                <span className="text-2xl font-bold text-white">{plan.price}</span>
              </div>

              <ul className="space-y-2">
                {plan.features.map((f, i) => (
                  <li key={i} className="flex items-center gap-2 text-sm text-gray-300 font-cairo">
                    <Check size={14} className="text-gold-primary shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>

              <button
                disabled={isCurrent}
                className={clsx(
                  'w-full py-2.5 rounded-lg text-sm font-semibold transition-all font-cairo',
                  isCurrent
                    ? 'bg-gray-800 text-gray-500 cursor-not-allowed'
                    : plan.highlight
                    ? 'bg-gradient-to-r from-gold-primary to-gold-dark text-gray-950 hover:opacity-90'
                    : 'bg-gray-800 text-white hover:bg-gray-700 border border-gray-700'
                )}
              >
                {isCurrent ? 'خطتك الحالية' : 'ترقية إلى ' + plan.nameAr}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
