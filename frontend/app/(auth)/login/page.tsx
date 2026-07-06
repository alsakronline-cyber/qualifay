'use client'

import { useState, FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import toast from 'react-hot-toast'
import { Eye, EyeOff, Loader2 } from 'lucide-react'
import { authApi } from '@/lib/api'

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!email || !password) {
      toast.error('يرجى إدخال البريد الإلكتروني أو الهاتف وكلمة المرور')
      return
    }
    setLoading(true)
    try {
      const res = await authApi.login(email, password)
      const { access_token } = res.data
      localStorage.setItem('auth_token', access_token)
      toast.success('تم تسجيل الدخول بنجاح')
      router.push('/leads')
    } catch (err: unknown) {
      const error = err as { response?: { data?: { message?: string } } }
      const msg =
        error?.response?.data?.message ||
        'فشل تسجيل الدخول. تحقق من بياناتك وحاول مجدداً.'
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      {/* Background gradient */}
      <div className="absolute inset-0 bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950 pointer-events-none" />
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[300px] bg-gold-primary/5 rounded-full blur-3xl pointer-events-none" />

      <div className="relative w-full max-w-md">
        {/* Logo / Brand */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-gold-primary to-gold-dark mb-4 shadow-lg shadow-gold-primary/20">
            <span className="text-2xl font-bold text-gray-950">Q</span>
          </div>
          <h1 className="text-3xl font-bold text-white font-cairo">Qualifay</h1>
          <p className="text-gray-400 mt-1 text-sm">نظام إدارة العملاء المحتملين بالذكاء الاصطناعي</p>
        </div>

        {/* Card */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 shadow-2xl">
          <h2 className="text-xl font-semibold text-white mb-6 font-cairo text-center">
            تسجيل الدخول / Login
          </h2>

          <form onSubmit={handleSubmit} className="space-y-5" noValidate>
            {/* Email or phone */}
            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium text-gray-300 mb-1.5 font-cairo"
              >
                البريد الإلكتروني أو الهاتف / Email or Phone
              </label>
              <input
                id="email"
                type="text"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com / +2010xxxxxxxx"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-gold-primary focus:border-transparent transition-all"
                dir="ltr"
              />
            </div>

            {/* Password */}
            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-gray-300 mb-1.5 font-cairo"
              >
                كلمة المرور / Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-gold-primary focus:border-transparent transition-all pr-10"
                  dir="ltr"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute inset-y-0 right-3 flex items-center text-gray-400 hover:text-gray-200 transition-colors"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-gradient-to-r from-gold-primary to-gold-dark hover:from-gold-dark hover:to-gold-primary text-gray-950 font-bold py-3 rounded-lg transition-all duration-200 flex items-center justify-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed shadow-lg shadow-gold-primary/20 font-cairo text-base"
            >
              {loading ? (
                <>
                  <Loader2 size={18} className="animate-spin" />
                  <span>جارٍ التحقق...</span>
                </>
              ) : (
                'تسجيل الدخول / Login'
              )}
            </button>
          </form>

          <p className="text-center text-sm text-gray-400 mt-6 font-cairo">
            ليس لديك حساب؟{' '}
            <Link href="/register" className="text-gold-primary hover:text-gold-dark font-semibold transition-colors">
              إنشاء حساب جديد
            </Link>
          </p>
        </div>

        <p className="text-center text-gray-600 text-xs mt-6">
          Qualifay &copy; {new Date().getFullYear()} — Powered by AI
        </p>
      </div>
    </div>
  )
}
