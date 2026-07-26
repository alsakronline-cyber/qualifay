'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Loader2, CheckCircle2, XCircle } from 'lucide-react'
import { authApi } from '@/lib/api'

export default function VerifyEmailPage() {
  const router = useRouter()
  const [state, setState] = useState<'working' | 'ok' | 'error'>('working')
  const [error, setError] = useState('')

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get('token') || ''
    if (!token) { setState('error'); setError('رابط التفعيل غير صالح'); return }
    authApi.verifyEmail(token)
      .then((r) => {
        localStorage.setItem('auth_token', r.data.access_token)
        setState('ok')
        setTimeout(() => router.push('/onboarding'), 1200)
      })
      .catch((e) => {
        setState('error')
        setError(e?.response?.data?.detail || 'انتهت صلاحية رابط التفعيل أو تم استخدامه')
      })
  }, [router])

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950 pointer-events-none" />
      <div className="relative w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-gold-primary to-gold-dark mb-4 shadow-lg shadow-gold-primary/20">
            <span className="text-2xl font-bold text-gray-950">Q</span>
          </div>
          <h1 className="text-3xl font-bold text-white font-cairo">Qualifay</h1>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 shadow-2xl text-center">
          {state === 'working' && (
            <div className="py-6 text-gray-300 font-cairo">
              <Loader2 size={26} className="mx-auto animate-spin text-gold-primary mb-3" />
              جارٍ تفعيل حسابك...
            </div>
          )}
          {state === 'ok' && (
            <div className="py-4">
              <CheckCircle2 size={40} className="mx-auto text-green-400 mb-3" />
              <p className="text-white font-cairo">تم تفعيل حسابك 🎉</p>
              <p className="text-gray-500 text-sm font-cairo mt-1">جارٍ تحويلك...</p>
            </div>
          )}
          {state === 'error' && (
            <div className="py-4">
              <XCircle size={40} className="mx-auto text-red-400 mb-3" />
              <p className="text-white font-cairo mb-1">{error}</p>
              <p className="text-gray-500 text-sm font-cairo mb-4">اطلب رابط تفعيل جديد من صفحة تسجيل الدخول.</p>
              <Link href="/login" className="text-gold-primary hover:text-gold-dark font-semibold text-sm">الذهاب لتسجيل الدخول</Link>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
