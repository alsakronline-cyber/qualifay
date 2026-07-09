'use client'

import { useState, useCallback } from 'react'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { UserPlus, Shield, User, Trash2, X } from 'lucide-react'
import { teamApi } from '@/lib/api'

interface Member { id: string; email: string; full_name: string; role: string; is_tenant_admin: boolean }

function InviteModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ email: '', full_name: '', password: '', is_admin: false })
  const [loading, setLoading] = useState(false)
  const set = (k: string, v: string | boolean) => setF((p) => ({ ...p, [k]: v }))

  async function save() {
    if (!f.email.trim() || !f.full_name.trim() || !f.password.trim()) { toast.error('أكمل جميع الحقول'); return }
    setLoading(true)
    try { await teamApi.invite(f); toast.success('تمت إضافة العضو'); onDone(); onClose() }
    catch (e: unknown) { const err = e as { response?: { data?: { detail?: string } } }; toast.error(err?.response?.data?.detail || 'فشلت الإضافة') }
    finally { setLoading(false) }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 w-full max-w-sm space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-white font-cairo">دعوة عضو</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-white"><X size={18} /></button>
        </div>
        {[['الاسم', 'full_name', 'text', 'rtl'], ['البريد الإلكتروني', 'email', 'email', 'ltr'], ['كلمة المرور', 'password', 'password', 'ltr']].map(([label, k, type, dir]) => (
          <div key={k}>
            <label className="block text-xs text-gray-400 font-cairo mb-1">{label}</label>
            <input type={type} dir={dir} value={String(f[k as keyof typeof f])} onChange={(e) => set(k, e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo" />
          </div>
        ))}
        <label className="flex items-center gap-2 text-sm text-gray-300 font-cairo">
          <input type="checkbox" checked={f.is_admin} onChange={(e) => set('is_admin', e.target.checked)} className="accent-gold-primary" /> صلاحيات مدير
        </label>
        <div className="flex gap-2 pt-2">
          <button onClick={onClose} className="flex-1 py-2.5 rounded-lg border border-gray-700 text-gray-400 hover:text-white text-sm font-cairo">إلغاء</button>
          <button onClick={save} disabled={loading} className="flex-1 py-2.5 rounded-lg bg-gold-primary text-gray-950 font-semibold text-sm disabled:opacity-50 font-cairo">{loading ? 'جارٍ...' : 'دعوة'}</button>
        </div>
      </div>
    </div>
  )
}

export default function TeamPage() {
  const { data, mutate, isLoading } = useSWR('team', () => teamApi.list().then((r) => r.data))
  const members: Member[] = Array.isArray(data) ? data : []
  const [inviting, setInviting] = useState(false)

  const act = useCallback(async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); toast.success(ok); mutate() }
    catch (e: unknown) { const err = e as { response?: { data?: { detail?: string } } }; toast.error(err?.response?.data?.detail || 'فشلت العملية') }
  }, [mutate])

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
          {members.map((m) => (
            <div key={m.id} className="flex items-center gap-3 px-4 py-3">
              <div className="w-9 h-9 rounded-full bg-gradient-to-br from-gold-primary/30 to-gold-dark/30 flex items-center justify-center text-sm font-bold text-gold-primary shrink-0">
                {m.full_name?.charAt(0) || m.email.charAt(0)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-white font-cairo truncate">{m.full_name}</div>
                <div className="text-xs text-gray-500 truncate" dir="ltr">{m.email}</div>
              </div>
              <span className={clsx('inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border font-cairo',
                m.is_tenant_admin ? 'text-gold-primary bg-gold-primary/10 border-gold-primary/30' : 'text-gray-400 bg-gray-700 border-gray-600')}>
                {m.is_tenant_admin ? <Shield size={11} /> : <User size={11} />} {m.is_tenant_admin ? 'مدير' : 'موظف'}
              </span>
              <button onClick={() => act(() => teamApi.update(m.id, { is_admin: !m.is_tenant_admin }), 'تم تحديث الصلاحية')}
                className="text-xs text-gray-400 hover:text-gold-primary font-cairo">
                {m.is_tenant_admin ? 'إلغاء الإدارة' : 'ترقية لمدير'}
              </button>
              <button onClick={() => { if (confirm('إزالة هذا العضو؟')) act(() => teamApi.remove(m.id), 'تمت الإزالة') }}
                className="text-gray-500 hover:text-red-400"><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
      )}

      {inviting && <InviteModal onClose={() => setInviting(false)} onDone={mutate} />}
    </div>
  )
}
