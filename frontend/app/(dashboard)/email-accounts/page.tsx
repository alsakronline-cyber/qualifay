'use client'

import { useState, useCallback } from 'react'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { Plus, Mail, Send, Trash2, Pause, Play, X, RefreshCw } from 'lucide-react'
import { emailApi } from '@/lib/api'

interface EmailAccount {
  id: string
  from_name?: string
  from_email: string
  smtp_host: string
  smtp_port: number
  imap_host?: string
  status: string
  paused: boolean
  sent_today: number
  warmup_day: number
  daily_cap: number
}

function AddModal({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const [f, setF] = useState({ from_email: '', from_name: '', smtp_host: 'smtp.hostinger.com', smtp_port: 465, smtp_password: '', imap_host: 'imap.hostinger.com', imap_port: 993 })
  const [loading, setLoading] = useState(false)
  const set = (k: string, v: string | number) => setF((p) => ({ ...p, [k]: v }))

  async function save() {
    if (!f.from_email.trim() || !f.smtp_password.trim() || !f.smtp_host.trim()) {
      toast.error('أدخل البريد وكلمة المرور وخادم SMTP'); return
    }
    setLoading(true)
    try {
      await emailApi.createAccount({ ...f, smtp_user: f.from_email })
      toast.success('تمت إضافة الحساب')
      onAdded(); onClose()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err?.response?.data?.detail || 'فشل إضافة الحساب')
    } finally { setLoading(false) }
  }

  const Field = ({ label, k, type = 'text', dir = 'ltr' }: { label: string; k: keyof typeof f; type?: string; dir?: string }) => (
    <div>
      <label className="block text-xs text-gray-400 font-cairo mb-1">{label}</label>
      <input type={type} dir={dir} value={String(f[k])} onChange={(e) => set(k, type === 'number' ? Number(e.target.value) : e.target.value)}
        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary" />
    </div>
  )

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 w-full max-w-md space-y-3 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-white font-cairo">إضافة حساب بريد</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-white"><X size={18} /></button>
        </div>
        <Field label="عنوان الإرسال (Email)" k="from_email" />
        <Field label="الاسم الظاهر" k="from_name" dir="rtl" />
        <Field label="كلمة مرور البريد (SMTP)" k="smtp_password" type="password" />
        <div className="grid grid-cols-2 gap-3">
          <Field label="خادم SMTP" k="smtp_host" />
          <Field label="منفذ SMTP" k="smtp_port" type="number" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="خادم IMAP (للردود)" k="imap_host" />
          <Field label="منفذ IMAP" k="imap_port" type="number" />
        </div>
        <div className="flex gap-2 pt-2">
          <button onClick={onClose} className="flex-1 py-2.5 rounded-lg border border-gray-700 text-gray-400 hover:text-white text-sm font-cairo">إلغاء</button>
          <button onClick={save} disabled={loading} className="flex-1 py-2.5 rounded-lg bg-gold-primary text-gray-950 font-semibold text-sm disabled:opacity-50 font-cairo">
            {loading ? 'جارٍ...' : 'إضافة'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function EmailAccountsPage() {
  const { data, mutate, isLoading } = useSWR('email/accounts', () => emailApi.listAccounts().then((r) => r.data))
  const accounts: EmailAccount[] = Array.isArray(data) ? data : []
  const [adding, setAdding] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)

  const act = useCallback(async (id: string, fn: () => Promise<unknown>, ok: string) => {
    setBusy(id)
    try { await fn(); toast.success(ok); mutate() }
    catch { toast.error('فشلت العملية') }
    finally { setBusy(null) }
  }, [mutate])

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white font-cairo">حسابات البريد</h1>
          <p className="text-gray-400 text-sm mt-1">Email Accounts — هويات إرسال متعددة تتناوب لزيادة الحجم</p>
        </div>
        <button onClick={() => setAdding(true)} className="flex items-center gap-1.5 bg-gold-primary text-gray-950 font-semibold text-sm px-4 py-2 rounded-lg font-cairo">
          <Plus size={16} /> إضافة حساب
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" /></div>
      ) : accounts.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          <Mail size={40} className="mx-auto mb-3 text-gray-700" />
          <p className="font-cairo">لا توجد حسابات بريد بعد</p>
          <p className="text-xs text-gray-600 mt-1">يتم استخدام حساب النظام الافتراضي حتى تضيف حساباتك</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {accounts.map((a) => (
            <div key={a.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
              <div className="flex items-start justify-between">
                <div className="min-w-0">
                  <h3 className="font-semibold text-white font-cairo truncate">{a.from_name || a.from_email}</h3>
                  <p className="text-xs text-gray-500 truncate" dir="ltr">{a.from_email}</p>
                </div>
                <span className={clsx('text-[10px] px-2 py-0.5 rounded-full border font-cairo shrink-0',
                  a.paused ? 'text-amber-400 bg-amber-500/10 border-amber-500/30'
                    : a.status === 'active' ? 'text-green-400 bg-green-500/10 border-green-500/30'
                    : 'text-gray-400 bg-gray-700 border-gray-600')}>
                  {a.paused ? 'متوقف مؤقتاً' : a.status === 'active' ? 'نشط' : 'معطّل'}
                </span>
              </div>

              <div className="bg-gray-800/50 rounded-lg p-2.5 text-xs text-gray-400 font-cairo">
                <div className="flex justify-between"><span>التسخين</span><span className="text-gray-200">اليوم {a.warmup_day}</span></div>
                <div className="flex justify-between mt-1"><span>اليوم</span><span className="text-gray-200">{a.sent_today}/{a.daily_cap}</span></div>
                <div className="mt-1.5 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                  <div className="h-full bg-gold-primary" style={{ width: `${Math.min(100, (a.sent_today / a.daily_cap) * 100)}%` }} />
                </div>
              </div>

              <div className="flex gap-2">
                <button onClick={() => act(a.id, () => emailApi.testAccount(a.id), 'تم إرسال رسالة اختبار')} disabled={busy === a.id}
                  className="flex-1 flex items-center justify-center gap-1 bg-gray-500/10 hover:bg-gray-500/20 text-gray-400 border border-gray-500/30 rounded-lg py-1.5 text-xs font-cairo disabled:opacity-50">
                  <Send size={12} /> اختبار
                </button>
                <button onClick={() => act(a.id, () => emailApi.updateAccount(a.id, { paused: !a.paused }), a.paused ? 'تم الاستئناف' : 'تم الإيقاف')} disabled={busy === a.id}
                  className={clsx('flex-1 flex items-center justify-center gap-1 rounded-lg py-1.5 text-xs font-cairo border disabled:opacity-50',
                    a.paused ? 'bg-green-500/10 text-green-400 border-green-500/30' : 'bg-amber-500/10 text-amber-400 border-amber-500/30')}>
                  {a.paused ? <><Play size={12} /> استئناف</> : <><Pause size={12} /> إيقاف</>}
                </button>
                <button onClick={() => { if (confirm('حذف هذا الحساب؟')) act(a.id, () => emailApi.deleteAccount(a.id), 'تم الحذف') }} disabled={busy === a.id}
                  className="shrink-0 flex items-center justify-center bg-gray-800 hover:bg-red-500/10 text-gray-400 hover:text-red-400 border border-gray-700 rounded-lg py-1.5 px-2.5 disabled:opacity-50">
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {adding && <AddModal onClose={() => setAdding(false)} onAdded={mutate} />}
    </div>
  )
}
