'use client'

import { useState, FormEvent, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import toast from 'react-hot-toast'
import { Eye, EyeOff, Loader2 } from 'lucide-react'
import { authApi } from '@/lib/api'

function slugify(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9؀-ۿ\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .slice(0, 40)
}

export default function RegisterPage() {
  const router = useRouter()
  const [companyName, setCompanyName] = useState('')
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleCompanyNameChange = useCallback((v: string) => {
    setCompanyName(v)
  }, [])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!companyName || !fullName || !email || !password) {
      toast.error('يرجى تعبئة كل الحقول المطلوبة')
      return
    }
    if (!email && !phone) {
      toast.error('يرجى إدخال البريد الإلكتروني أو رقم الهاتف')
      return
    }
    if (password.length < 8) {
      toast.error('كلمة المرور يجب أن تكون 8 أحرف على الأقل')
      return
    }
    if (password !== confirmPassword) {
      toast.error('كلمتا المرور غير متطابقتين')
      return
    }

    setLoading(true)
    try {
      const res = await authApi.register({
        tenant_name: companyName,
        tenant_slug: slugify(companyName) || `tenant-${Date.now()}`,
        full_name: fullName,
        email,
        phone: phone || undefined,
        password,
        language: 'ar',
      })
      const { access_token } = res.data
      localStorage.setItem('auth_token', access_token)
      toast.success('تم إنشاء الحساب بنجاح')
      router.push('/onboarding')
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      const msg = error?.response?.data?.detail || 'فشل إنشاء الحساب. حاول مجدداً.'
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4 py-10">
      <div className="absolute inset-0 bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950 pointer-events-none" />
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[300px] bg-gold-primary/5 rounded-full blur-3xl pointer-events-none" />

      <div className="relative w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-gold-primary to-gold-dark mb-4 shadow-lg shadow-gold-primary/20">
            <span className="text-2xl font-bold text-gray-950">Q</span>
          </div>
          <h1 className="text-3xl font-bold text-white font-cairo">Qualifay</h1>
          <p className="text-gray-400 mt-1 text-sm">ابدأ تجربتك المجانية لمدة 30 يوماً</p>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 shadow-2xl">
          <h2 className="text-xl font-semibold text-white mb-6 font-cairo text-center">
            إنشاء حساب جديد / Create Account
          </h2>

          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <div>
              <label htmlFor="companyName" className="block text-sm font-medium text-gray-300 mb-1.5 font-cairo">
                اسم الشركة / Company Name
              </label>
              <input
                id="companyName"
                type="text"
                value={companyName}
                onChange={(e) => handleCompanyNameChange(e.target.value)}
                placeholder="شركة النور للمقاولات"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-gold-primary focus:border-transparent transition-all"
              />
            </div>

            <div>
              <label htmlFor="fullName" className="block text-sm font-medium text-gray-300 mb-1.5 font-cairo">
                الاسم الكامل / Full Name
              </label>
              <input
                id="fullName"
                type="text"
                autoComplete="name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="محمد أحمد"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-gold-primary focus:border-transparent transition-all"
              />
            </div>

            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-300 mb-1.5 font-cairo">
                البريد الإلكتروني / Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-gold-primary focus:border-transparent transition-all"
                dir="ltr"
              />
            </div>

            <div>
              <label htmlFor="phone" className="block text-sm font-medium text-gray-300 mb-1.5 font-cairo">
                رقم الهاتف / Phone <span className="text-gray-600">(اختياري — للدخول أيضاً بالهاتف)</span>
              </label>
              <input
                id="phone"
                type="tel"
                autoComplete="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+201xxxxxxxxx"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-gold-primary focus:border-transparent transition-all"
                dir="ltr"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-300 mb-1.5 font-cairo">
                كلمة المرور / Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
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

            <div>
              <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-300 mb-1.5 font-cairo">
                تأكيد كلمة المرور / Confirm Password
              </label>
              <input
                id="confirmPassword"
                type={showPassword ? 'text' : 'password'}
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-gold-primary focus:border-transparent transition-all"
                dir="ltr"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-gradient-to-r from-gold-primary to-gold-dark hover:from-gold-dark hover:to-gold-primary text-gray-950 font-bold py-3 rounded-lg transition-all duration-200 flex items-center justify-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed shadow-lg shadow-gold-primary/20 font-cairo text-base"
            >
              {loading ? (
                <>
                  <Loader2 size={18} className="animate-spin" />
                  <span>جارٍ الإنشاء...</span>
                </>
              ) : (
                'إنشاء الحساب / Sign Up'
              )}
            </button>
          </form>

          <p className="text-center text-sm text-gray-400 mt-6 font-cairo">
            لديك حساب بالفعل؟{' '}
            <Link href="/login" className="text-gold-primary hover:text-gold-dark font-semibold transition-colors">
              تسجيل الدخول
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
