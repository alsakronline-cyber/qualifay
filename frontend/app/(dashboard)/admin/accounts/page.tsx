'use client'

import { useState } from 'react'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { UsersRound, Search, ShieldCheck, Shield, User, CheckCircle2, Ban, Play, KeyRound, Trash2, X } from 'lucide-react'
import { adminApi } from '@/lib/api'

interface Acct {
  id: string; email: string; full_name: string; company: string; tenant_id: string
  is_admin: boolean; is_tenant_admin: boolean; role: string; status: string; created_at: string | null
}

function PwModal({ acct, onClose }: { acct: Acct; onClose: () => void }) {
  const [pw, setPw] = useState(''); const [saving, setSaving] = useState(false)
  async function save() {
    if (pw.length < 8) return toast.error('8 أحرف على الأقل')
    setSaving(true)
    try { await adminApi.setPassword(acct.id, pw); toast.success('تم تعيين كلمة المرور'); onClose() }
    catch (e: unknown) { toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'فشل') }
    finally { setSaving(false) }
  }
  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 w-full max-w-sm space-y-3" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between"><h3 className="font-semibold text-white font-cairo">كلمة مرور جديدة</h3><button onClick={onClose} className="text-gray-500 hover:text-white"><X size={18} /></button></div>
        <p className="text-xs text-gray-400 font-cairo" dir="ltr">{acct.email}</p>
        <input type="text" dir="ltr" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="كلمة المرور الجديدة"
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary" />
        <button onClick={save} disabled={saving} className="w-full py-2.5 rounded-lg bg-gold-primary text-gray-950 font-semibold text-sm disabled:opacity-50 font-cairo">{saving ? 'جارٍ...' : 'حفظ'}</button>
      </div>
    </div>
  )
}

export default function AdminAccountsPage() {
  const [search, setSearch] = useState('')
  const { data, mutate, isLoading } = useSWR(['admin-users', search], () => adminApi.users(search || undefined).then((r) => r.data))
  const accts: Acct[] = Array.isArray(data) ? data : []
  const [busy, setBusy] = useState<string | null>(null)
  const [pwFor, setPwFor] = useState<Acct | null>(null)

  async function act(fn: () => Promise<unknown>, ok: string) {
    try { await fn(); toast.success(ok); await mutate() }
    catch (e: unknown) { toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'فشل') }
  }
  const upd = (id: string, body: Record<string, unknown>, ok: string) => act(() => adminApi.updateUser(id, body), ok)

  const roleBadge = (a: Acct) => a.is_admin
    ? { t: 'مالك المنصة', c: 'text-gold-primary bg-gold-primary/10 border-gold-primary/30', I: ShieldCheck }
    : a.is_tenant_admin ? { t: 'مدير', c: 'text-gray-400 bg-gray-500/10 border-gray-500/30', I: Shield }
    : { t: 'موظف', c: 'text-gray-400 bg-gray-700 border-gray-600', I: User }

  return (
    <div className="space-y-5 max-w-5xl">
      <div className="flex items-center gap-2">
        <UsersRound size={20} className="text-gold-primary" />
        <div><h1 className="text-2xl font-bold text-white font-cairo">الحسابات</h1><p className="text-gray-400 text-sm font-cairo">كل مستخدمي المنصة</p></div>
      </div>

      <div className="relative max-w-sm">
        <Search size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500" />
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="ابحث بالبريد أو الاسم..."
          className="w-full bg-gray-900 border border-gray-800 rounded-lg pr-9 pl-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo" />
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" /></div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-xl divide-y divide-gray-800">
          {accts.map((a) => {
            const rb = roleBadge(a); const RI = rb.I
            const suspended = a.status === 'suspended'; const unverified = a.status === 'unverified'
            return (
              <div key={a.id} className="flex items-center gap-3 px-4 py-3 flex-wrap">
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-white font-cairo truncate">{a.full_name || a.email.split('@')[0]}</div>
                  <div className="text-xs text-gray-500 truncate flex items-center gap-1.5" dir="ltr">
                    <span className="truncate">{a.email}</span>
                    {a.company && <span className="text-gray-600 shrink-0 font-cairo" dir="rtl">· {a.company}</span>}
                  </div>
                </div>
                <span className={clsx('inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border font-cairo', rb.c)}><RI size={11} /> {rb.t}</span>
                {suspended && <span className="text-[10px] bg-red-500/20 text-red-300 rounded-full px-2 py-0.5 font-cairo">موقوف</span>}
                {unverified && <span className="text-[10px] bg-gray-500/20 text-gray-300 rounded-full px-2 py-0.5 font-cairo">غير مُفعّل</span>}

                <div className="flex items-center gap-1.5">
                  {unverified && (
                    <button onClick={() => upd(a.id, { status: 'active' }, 'تم تفعيل الحساب')} title="تفعيل البريد يدوياً"
                      className="text-green-400 hover:text-green-300"><CheckCircle2 size={15} /></button>
                  )}
                  {!unverified && (suspended
                    ? <button onClick={() => upd(a.id, { status: 'active' }, 'تم التفعيل')} title="تفعيل" className="text-green-400 hover:text-green-300"><Play size={15} /></button>
                    : <button onClick={() => upd(a.id, { status: 'suspended' }, 'تم الإيقاف')} title="إيقاف" className="text-gray-400 hover:text-red-400"><Ban size={15} /></button>)}
                  {!a.is_admin && (
                    <button onClick={() => upd(a.id, { is_tenant_admin: !a.is_tenant_admin }, 'تم تحديث الصلاحية')} className="text-[11px] text-gray-400 hover:text-gold-primary font-cairo">
                      {a.is_tenant_admin ? 'إلغاء الإدارة' : 'ترقية لمدير'}
                    </button>
                  )}
                  <button onClick={() => setPwFor(a)} title="تعيين كلمة مرور" className="text-gray-400 hover:text-gold-primary"><KeyRound size={14} /></button>
                  <button onClick={() => { if (confirm(`حذف حساب ${a.email}؟`)) act(() => adminApi.deleteUser(a.id), 'تم الحذف') }} title="حذف" className="text-gray-500 hover:text-red-400"><Trash2 size={14} /></button>
                </div>
              </div>
            )
          })}
          {accts.length === 0 && <p className="text-center text-gray-600 text-sm py-8 font-cairo">لا نتائج</p>}
        </div>
      )}

      {pwFor && <PwModal acct={pwFor} onClose={() => { setPwFor(null); mutate() }} />}
    </div>
  )
}
