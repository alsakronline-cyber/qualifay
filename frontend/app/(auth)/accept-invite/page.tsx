'use client'

import { useState, useEffect, FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import toast from 'react-hot-toast'
import { Eye, EyeOff, Loader2, CheckCircle2, XCircle } from 'lucide-react'
import { authApi } from '@/lib/api'

interface Invite { email: string; full_name: string; company: string; role: string }

export default function AcceptInvitePage() {
  const router = useRouter()
  const [token, setToken] = useState('')
  const [invite, setInvite] = useState<Invite | null>(null)
  const [loadError, setLoadError] = useState('')
  const [loadingInvite, setLoadingInvite] = useState(true)

  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  // Read the token client-side (avoids the useSearchParams Suspense build constraint).
  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get('token') || ''
    setToken(t)
    if (!t) { setLoadError('رابط الدعوة غير صالح'); setLoadingInvite(false); return }
    authApi.getInvite(t)
      .then((r) => { setInvite(r.data); setFullName(r.data.full_name || '') })
      .catch((e) => setLoadError(e?.response?.data?.detail || 'انتهت صلاحية الدعوة أو تم استخدامها'))
      .finally(() => setLoadingInvite(false))
  }, [])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!fullName.trim()) return toast.error('يرجى إدخال اسمك')
    if (password.length < 8) return toast.error('كلمة المرور يجب أن تكون 8 أحرف على الأقل')
    if (password !== confirm) return toast.error('كلمتا المرور غير متطابقتين')
    setSubmitting(true)
    try {
      const res = await authApi.acceptInvite({ token, full_name: fullName.trim(), password })
      localStorage.setItem('auth_token', res.data.access_token)
      toast.success('تم تفعيل حسابك! أهلاً بك 🎉')
      router.push('/')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(msg || 'تعذّر تفعيل الحساب')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950 pointer-events-none" />
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[300px] bg-gold-primary/5 rounded-full blur-3xl pointer-events-none" />

      <div className="relative w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-gold-primary to-gold-dark mb-4 shadow-lg shadow-gold-primary/20">
            <span className="text-2xl font-bold text-gray-950">Q</span>
          </div>
          <h1 className="text-3xl font-bold text-white font-cairo">Qualifay</h1>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 shadow-2xl">
          {loadingInvite ? (
            <div className="flex items-center justify-center py-10 text-gray-400">
              <Loader2 size={22} className="animate-spin" />
            </div>
          ) : loadError ? (
            <div className="text-center py-6">
              <XCircle size={40} className="mx-auto text-red-400 mb-3" />
              <p className="text-white font-cairo mb-1">{loadError}</p>
              <p className="text-gray-500 text-sm font-cairo mb-4">اطلب من مدير الفريق إرسال دعوة جديدة.</p>
              <Link href="/login" className="text-gold-primary hover:text-gold-dark font-semibold text-sm">
                الذهاب لتسجيل الدخول
              </Link>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2 mb-1 justify-center">
                <CheckCircle2 size={18} className="text-gold-primary" />
                <h2 className="text-lg font-semibold text-white font-cairo">دعوة للانضمام</h2>
              </div>
              <p className="text-center text-sm text-gray-400 font-cairo mb-6">
                تمت دعوتك للانضمام إلى فريق <span className="text-gold-primary font-semibold">{invite?.company}</span>
                {' '}كـ{invite?.role === 'admin' ? ' مدير' : ' عضو'}. عيّن كلمة المرور لتفعيل حسابك.
              </p>

              <form onSubmit={handleSubmit} className="space-y-4" noValidate>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1.5 font-cairo">البريد الإلكتروني</label>
                  <input value={invite?.email || ''} disabled dir="ltr"
                    className="w-full bg-gray-800/60 border border-gray-700 rounded-lg px-4 py-2.5 text-gray-400" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1.5 font-cairo">اسمك الكامل</label>
                  <input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="الاسم"
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-gold-primary font-cairo" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1.5 font-cairo">كلمة المرور</label>
                  <div className="relative">
                    <input type={showPassword ? 'text' : 'password'} value={password}
                      onChange={(e) => setPassword(e.target.value)} placeholder="8 أحرف على الأقل" dir="ltr"
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-gold-primary pr-10" />
                    <button type="button" onClick={() => setShowPassword((v) => !v)} tabIndex={-1}
                      className="absolute inset-y-0 right-3 flex items-center text-gray-400 hover:text-gray-200">
                      {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1.5 font-cairo">تأكيد كلمة المرور</label>
                  <input type={showPassword ? 'text' : 'password'} value={confirm}
                    onChange={(e) => setConfirm(e.target.value)} placeholder="••••••••" dir="ltr"
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-gold-primary" />
                </div>

                <button type="submit" disabled={submitting}
                  className="w-full bg-gradient-to-r from-gold-primary to-gold-dark text-gray-950 font-bold py-3 rounded-lg transition-all flex items-center justify-center gap-2 disabled:opacity-60 font-cairo">
                  {submitting ? <><Loader2 size={18} className="animate-spin" /> جارٍ التفعيل...</> : 'تفعيل الحساب والدخول'}
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
