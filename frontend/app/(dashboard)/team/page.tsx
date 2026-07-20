'use client'

import { useState, useCallback } from 'react'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { UserPlus, Shield, User, Trash2, X, Copy, Check, Clock, Mail, Send } from 'lucide-react'
import { teamApi } from '@/lib/api'

interface Member {
  id: string; email: string; full_name: string; role: string
  is_tenant_admin: boolean; status?: string
}

function CopyField({ url }: { url: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="flex items-stretch gap-2">
      <input readOnly value={url} dir="ltr"
        onFocus={(e) => e.target.select()}
        className="flex-1 min-w-0 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-xs text-gray-300" />
      <button
        onClick={() => { navigator.clipboard.writeText(url).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) }) }}
        className="shrink-0 flex items-center gap-1 bg-gold-primary text-gray-950 rounded-lg px-3 text-xs font-semibold font-cairo">
        {copied ? <Check size={13} /> : <Copy size={13} />}{copied ? 'تم' : 'نسخ'}
      </button>
    </div>
  )
}

function InviteModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ email: '', full_name: '', is_admin: false })
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{ url: string; email_sent: boolean } | null>(null)
  const set = (k: string, v: string | boolean) => setF((p) => ({ ...p, [k]: v }))

  async function save() {
    if (!f.email.trim()) { toast.error('أدخل البريد الإلكتروني'); return }
    setLoading(true)
    try {
      const r = await teamApi.invite({ email: f.email.trim(), full_name: f.full_name.trim(), is_admin: f.is_admin })
      setResult({ url: r.data.invite_url, email_sent: r.data.email_sent })
      onDone()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err?.response?.data?.detail || 'فشلت الدعوة')
    } finally { setLoading(false) }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 w-full max-w-sm space-y-3" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-white font-cairo">{result ? 'تم إرسال الدعوة' : 'دعوة عضو'}</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-white"><X size={18} /></button>
        </div>

        {result ? (
          <div className="space-y-3">
            <p className="text-sm text-gray-300 font-cairo leading-relaxed">
              {result.email_sent
                ? 'أُرسلت الدعوة بالبريد. يمكنك أيضاً مشاركة الرابط مباشرةً:'
                : 'تعذّر إرسال البريد — شارك رابط الدعوة يدوياً (واتساب مثلاً):'}
            </p>
            <CopyField url={result.url} />
            <p className="text-[11px] text-gray-500 font-cairo">الرابط صالح لمدة 7 أيام. يعيّن العضو كلمة مروره بنفسه عند فتحه.</p>
            <button onClick={onClose} className="w-full py-2.5 rounded-lg bg-gold-primary text-gray-950 font-semibold text-sm font-cairo">تم</button>
          </div>
        ) : (
          <>
            <div>
              <label className="block text-xs text-gray-400 font-cairo mb-1">البريد الإلكتروني</label>
              <input type="email" dir="ltr" value={f.email} onChange={(e) => set('email', e.target.value)}
                placeholder="teammate@company.com"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 font-cairo mb-1">الاسم (اختياري)</label>
              <input dir="rtl" value={f.full_name} onChange={(e) => set('full_name', e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo" />
            </div>
            <label className="flex items-center gap-2 text-sm text-gray-300 font-cairo">
              <input type="checkbox" checked={f.is_admin} onChange={(e) => set('is_admin', e.target.checked)} className="accent-gold-primary" /> صلاحيات مدير
            </label>
            <div className="flex gap-2 pt-2">
              <button onClick={onClose} className="flex-1 py-2.5 rounded-lg border border-gray-700 text-gray-400 hover:text-white text-sm font-cairo">إلغاء</button>
              <button onClick={save} disabled={loading} className="flex-1 py-2.5 rounded-lg bg-gold-primary text-gray-950 font-semibold text-sm disabled:opacity-50 font-cairo">{loading ? 'جارٍ...' : 'إرسال الدعوة'}</button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default function TeamPage() {
  const { data, mutate, isLoading } = useSWR('team', () => teamApi.list().then((r) => r.data))
  const members: Member[] = Array.isArray(data) ? data : []
  const [inviting, setInviting] = useState(false)
  const [resendUrl, setResendUrl] = useState<string | null>(null)

  const act = useCallback(async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); toast.success(ok); mutate() }
    catch (e: unknown) { const err = e as { response?: { data?: { detail?: string } } }; toast.error(err?.response?.data?.detail || 'فشلت العملية') }
  }, [mutate])

  async function resend(id: string) {
    try {
      const r = await teamApi.resend(id)
      setResendUrl(r.data.invite_url)
      toast.success(r.data.email_sent ? 'أُعيد إرسال الدعوة بالبريد' : 'تم توليد رابط جديد')
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err?.response?.data?.detail || 'فشل')
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white font-cairo">الفريق</h1>
          <p className="text-gray-400 text-sm mt-1">Team — أعضاء الفريق وصلاحياتهم</p>
        </div>
        <button onClick={() => setInviting(true)} className="flex items-center gap-1.5 bg-gold-primary text-gray-950 font-semibold text-sm px-4 py-2 rounded-lg font-cairo">
          <UserPlus size={16} /> دعوة عضو
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" /></div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-xl divide-y divide-gray-800">
          {members.map((m) => {
            const pending = m.status === 'invited'
            return (
              <div key={m.id} className="flex items-center gap-3 px-4 py-3">
                <div className={clsx('w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold shrink-0',
                  pending ? 'bg-gray-800 text-gray-500' : 'bg-gradient-to-br from-gold-primary/30 to-gold-dark/30 text-gold-primary')}>
                  {(m.full_name?.charAt(0) || m.email.charAt(0)).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-white font-cairo truncate">{m.full_name || m.email.split('@')[0]}</div>
                  <div className="text-xs text-gray-500 truncate" dir="ltr">{m.email}</div>
                </div>
                {pending ? (
                  <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border text-yellow-400 bg-yellow-500/10 border-yellow-500/30 font-cairo">
                    <Clock size={11} /> بانتظار القبول
                  </span>
                ) : (
                  <span className={clsx('inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border font-cairo',
                    m.is_tenant_admin ? 'text-gold-primary bg-gold-primary/10 border-gold-primary/30' : 'text-gray-400 bg-gray-700 border-gray-600')}>
                    {m.is_tenant_admin ? <Shield size={11} /> : <User size={11} />} {m.is_tenant_admin ? 'مدير' : 'موظف'}
                  </span>
                )}
                {pending ? (
                  <button onClick={() => resend(m.id)} title="إعادة إرسال الدعوة"
                    className="flex items-center gap-1 text-xs text-gray-400 hover:text-gold-primary font-cairo"><Send size={13} /> إعادة إرسال</button>
                ) : (
                  <button onClick={() => act(() => teamApi.update(m.id, { is_admin: !m.is_tenant_admin }), 'تم تحديث الصلاحية')}
                    className="text-xs text-gray-400 hover:text-gold-primary font-cairo">
                    {m.is_tenant_admin ? 'إلغاء الإدارة' : 'ترقية لمدير'}
                  </button>
                )}
                <button onClick={() => { if (confirm(pending ? 'إلغاء هذه الدعوة؟' : 'إزالة هذا العضو؟')) act(() => teamApi.remove(m.id), 'تم') }}
                  className="text-gray-500 hover:text-red-400"><Trash2 size={14} /></button>
              </div>
            )
          })}
        </div>
      )}

      {inviting && <InviteModal onClose={() => setInviting(false)} onDone={mutate} />}

      {resendUrl && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={() => setResendUrl(null)}>
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 w-full max-w-sm space-y-3" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2"><Mail size={16} className="text-gold-primary" /><h3 className="font-semibold text-white font-cairo">رابط الدعوة</h3></div>
            <CopyField url={resendUrl} />
            <button onClick={() => setResendUrl(null)} className="w-full py-2.5 rounded-lg bg-gold-primary text-gray-950 font-semibold text-sm font-cairo">تم</button>
          </div>
        </div>
      )}
    </div>
  )
}
