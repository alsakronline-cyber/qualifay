'use client'

import { useState, useCallback, useEffect } from 'react'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { Plus, QrCode, RefreshCw, Wifi, WifiOff, AlertTriangle, X, Trash2, Download, Pause, Play } from 'lucide-react'
import { instancesApi } from '@/lib/api'
import type { WaInstance } from '@/lib/types'
import { dashboardApi } from '@/lib/api'
import { NUMBER_STATE, QUIET_DAYS, FULL_DAYS, type NumberRow } from '@/lib/wa-state'

function PairingPanel({ instanceId }: { instanceId: string }) {
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function getCode() {
    if (!phone.trim()) { toast.error('اكتب رقم الواتساب أولاً'); return }
    setLoading(true); setCode(null)
    try {
      const r = await instancesApi.pairingCode(instanceId, phone.trim())
      setCode(r.data.pairing_code)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err?.response?.data?.detail || 'تعذّر إنشاء الكود')
    } finally { setLoading(false) }
  }

  const pretty = code && code.length === 8 ? `${code.slice(0, 4)}-${code.slice(4)}` : code

  return (
    <div className="space-y-3">
      <label className="block text-xs text-gray-400 font-cairo">رقم الواتساب الذي تريد ربطه</label>
      <div className="flex gap-2">
        <input dir="ltr" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && getCode()} placeholder="01012345678"
          className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary" />
        <button onClick={getCode} disabled={loading}
          className="px-4 rounded-lg bg-gold-primary text-gray-950 font-semibold text-sm font-cairo disabled:opacity-50">
          {loading ? '...' : code ? 'كود جديد' : 'إنشاء الكود'}
        </button>
      </div>
      {loading && <p className="text-xs text-gray-500 font-cairo">جارٍ تجهيز الكود — قد يستغرق حتى 10 ثوانٍ</p>}
      {pretty && (
        <div className="text-center space-y-2 pt-1">
          <div dir="ltr" className="text-3xl font-mono font-bold tracking-[0.2em] text-gold-primary select-all">{pretty}</div>
          <button onClick={() => { navigator.clipboard?.writeText(code!); toast.success('تم النسخ') }}
            className="text-xs text-gray-400 hover:text-white underline font-cairo">نسخ الكود</button>
        </div>
      )}
      <ol className="text-xs text-gray-400 font-cairo space-y-1 list-decimal pr-4 pt-1">
        <li>افتح واتساب على هذا الرقم ← الأجهزة المرتبطة ← ربط جهاز</li>
        <li>اضغط «الربط برقم الهاتف بدلاً من ذلك»</li>
        <li>اكتب الكود خلال دقيقة واحدة</li>
      </ol>
    </div>
  )
}

function QrModal({ instanceId, onClose, onConnected, initialMode = 'qr' }: {
  instanceId: string; onClose: () => void; onConnected?: () => void; initialMode?: 'qr' | 'phone'
}) {
  const [mode, setMode] = useState<'qr' | 'phone'>(initialMode)
  // A WhatsApp QR expires (~1 min unscanned) and the session closes; on open, ask the
  // backend to regenerate a fresh QR (logout+connect) before we start polling for it.
  useEffect(() => {
    if (mode === 'qr') instancesApi.reconnect(instanceId).catch(() => {})
  }, [instanceId, mode])
  const { data, isLoading, error } = useSWR(
    mode === 'qr' ? `instances/${instanceId}/qr` : null,
    () => instancesApi.getQr(instanceId).then((r) => r.data),
    { refreshInterval: 3000 }
  )
  // Close by itself the moment the phone finishes linking, whichever method was used.
  const { data: st } = useSWR(`instances/${instanceId}/status`,
    () => instancesApi.getStatus(instanceId).then((r) => r.data), { refreshInterval: 3000 })
  const linked = ['open', 'connected'].includes(String(st?.state || st?.status || st?.instance?.state || ''))
  useEffect(() => {
    if (!linked) return
    toast.success('تم ربط الرقم بنجاح ✅')
    onConnected?.(); onClose()
  }, [linked]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 w-full max-w-sm relative">
        <button
          onClick={onClose}
          aria-label="إغلاق"
          className="absolute top-4 left-4 text-gray-400 hover:text-white"
        >
          <X size={18} />
        </button>
        <h3 className="text-lg font-semibold text-white font-cairo text-center mb-4">
          ربط رقم واتساب
        </h3>
        <div className="grid grid-cols-2 gap-1 p-1 mb-4 bg-gray-800 rounded-lg text-sm font-cairo" role="tablist">
          {([['qr', 'مسح رمز QR'], ['phone', 'برقم الهاتف']] as const).map(([k, l]) => (
            <button key={k} role="tab" aria-selected={mode === k} onClick={() => setMode(k)}
              className={clsx('py-1.5 rounded-md transition-colors',
                mode === k ? 'bg-gray-950 text-white font-semibold' : 'text-gray-400 hover:text-white')}>
              {l}
            </button>
          ))}
        </div>
        {mode === 'phone' && <PairingPanel instanceId={instanceId} />}
        {isLoading && (
          <div className="flex justify-center py-8">
            <div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" />
          </div>
        )}
        {error && !data?.qr_code && (
          <p className="text-center text-red-400 font-cairo text-sm py-4">
            جاري تجهيز رمز QR... لحظات من فضلك.
          </p>
        )}
        {data?.qr_code && (
          <div className="flex flex-col items-center gap-3">
            <img
              src={data.qr_code.startsWith('data:') ? data.qr_code : `data:image/png;base64,${data.qr_code}`}
              alt="QR Code"
              className="w-56 h-56 rounded-lg bg-white p-2"
            />
            <p className="text-xs text-gray-500 font-cairo text-center">
              يتجدد الرمز كل 20 ثانية. افتح واتساب → الأجهزة المرتبطة → ربط جهاز
            </p>
            <button onClick={() => setMode('phone')} className="text-xs text-gold-primary hover:underline font-cairo">
              ظهرت رسالة «تعذّر ربط الجهاز»؟ اربط برقم الهاتف بدلاً من ذلك
            </button>
          </div>
        )}
        {data?.qr_image_url && !data?.qr_code && (
          <img
            src={data.qr_image_url}
            alt="QR Code"
            className="w-56 h-56 rounded-lg bg-white p-2 mx-auto"
          />
        )}
      </div>
    </div>
  )
}


function DeleteConfirmModal({ instance, onClose, onDeleted }: { instance: WaInstance; onClose: () => void; onDeleted: () => void }) {
  const [loading, setLoading] = useState(false)
  const [purge, setPurge] = useState(false)
  async function handleDelete() {
    setLoading(true)
    try {
      await instancesApi.delete(instance.id, purge)
      toast.success(purge ? 'تم فصل الرقم وحذف سجل المحادثات' : 'تم فصل الرقم — تم الاحتفاظ بالمحادثات والعملاء')
      onDeleted()
      onClose()
    } catch {
      toast.error('فشل حذف النسخة')
    } finally {
      setLoading(false)
    }
  }
  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 w-full max-w-sm">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 bg-red-500/10 rounded-full flex items-center justify-center">
            <Trash2 size={18} className="text-red-400" />
          </div>
          <div>
            <h3 className="font-semibold text-white font-cairo">فصل الرقم</h3>
            <p className="text-sm text-gray-400 font-cairo">{instance.display_name || instance.instance_name}</p>
          </div>
        </div>
        {/* Clarify that this disconnects a channel, it does not erase records. */}
        <p className="text-sm text-gray-300 font-cairo mb-2 leading-relaxed">
          سيتم فصل رقم واتساب. يتم <span className="text-green-400">الاحتفاظ بالمحادثات والعملاء المحتملين</span> افتراضياً — تظهر المحادثات في صندوق الوارد كـ "غير متصل".
        </p>
        {/* Explicit, opt-in erasure — never the default. */}
        <label className="flex items-start gap-2 mb-5 mt-3 p-2.5 rounded-lg bg-red-500/5 border border-red-500/20 cursor-pointer">
          <input type="checkbox" checked={purge} onChange={(e) => setPurge(e.target.checked)} className="mt-0.5 accent-red-500" />
          <span className="text-xs text-red-300 font-cairo leading-relaxed">
            حذف سجل المحادثات أيضاً (لا يمكن التراجع). العملاء المحتملون في خط الأنابيب لا يُحذفون.
          </span>
        </label>
        <div className="flex gap-2">
          <button onClick={onClose} className="flex-1 py-2.5 rounded-lg border border-gray-700 text-gray-400 hover:text-white text-sm transition-colors font-cairo">إلغاء</button>
          <button onClick={handleDelete} disabled={loading} className="flex-1 py-2.5 rounded-lg bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-400 font-semibold text-sm disabled:opacity-50 transition-all font-cairo">
            {loading ? 'جارٍ...' : (purge ? 'فصل وحذف السجل' : 'فصل الرقم')}
          </button>
        </div>
      </div>
    </div>
  )
}
function AddInstanceModal({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleCreate() {
    if (!name.trim()) return
    setLoading(true)
    try {
      await instancesApi.create(name.trim())
      toast.success('تم إنشاء النسخة بنجاح')
      onAdded()
      onClose()
    } catch {
      toast.error('فشل إنشاء النسخة')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 w-full max-w-sm">
        <h3 className="text-lg font-semibold text-white font-cairo mb-4">إضافة نسخة واتساب</h3>
        <input
          type="text"
          placeholder="اسم النسخة (مثال: رقم المبيعات)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleCreate() }}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo text-sm mb-4"
          autoFocus
        />
        <div className="flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 py-2.5 rounded-lg border border-gray-700 text-gray-400 hover:text-white text-sm transition-colors font-cairo"
          >
            إلغاء
          </button>
          <button
            onClick={handleCreate}
            disabled={loading || !name.trim()}
            className="flex-1 py-2.5 rounded-lg bg-gradient-to-r from-gold-primary to-gold-dark text-gray-950 font-semibold text-sm disabled:opacity-50 transition-all font-cairo"
          >
            {loading ? 'جارٍ الإنشاء...' : 'إنشاء'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function InstancesPage() {
  const { data, mutate, isLoading } = useSWR(
    'instances',
    () => instancesApi.list().then((r) => r.data),
    { refreshInterval: 15000 }
  )
  const instances: WaInstance[] = data?.items || data || []

  // Client-facing state (protection period, campaign limit) — same source as the home page.
  const { data: home, mutate: mutateHome } = useSWR('/dashboard/home',
    () => dashboardApi.home().then((r) => r.data), { refreshInterval: 30000 })
  const health: Record<string, NumberRow> = Object.fromEntries(
    ((home?.numbers || []) as NumberRow[]).map((n) => [n.id, n]))
  const refresh = () => { mutate(); mutateHome() }

  const [qrModal, setQrModal] = useState<{ id: string; mode: 'qr' | 'phone' } | null>(null)
  const [addModal, setAddModal] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<WaInstance | null>(null)

  const handleSync = useCallback(async (id: string) => {
    try {
      await instancesApi.sync(id)
      toast.success('تمت مزامنة المحادثات')
      mutate()
    } catch { toast.error('فشل المزامنة') }
  }, [mutate])

  const handlePause = useCallback(async (id: string, paused: boolean) => {
    try {
      await instancesApi.pause(id, paused)
      toast.success(paused ? 'تم إيقاف الإرسال مؤقتاً' : 'تم استئناف الإرسال')
      mutate()
    } catch {
      toast.error('فشل تغيير الحالة')
    }
  }, [mutate])

  const handleDisconnect = useCallback(async (id: string) => {
    // Real logout — gated behind a confirm because it needs a QR re-scan to restore.
    if (!confirm('تسجيل الخروج يفصل الرقم عن واتساب وستحتاج لإعادة ربطه. لإيقاف الحملات فقط دون فصل الرقم استخدم «إيقاف الحملات». متابعة؟')) return
    try {
      await instancesApi.disconnect(id)
      toast.success('تم قطع الاتصال')
      mutate()
    } catch {
      toast.error('فشل قطع الاتصال')
    }
  }, [mutate])

  const getStatusConfig = (status: string) => {
    switch (status) {
      case 'open':
      case 'connected': return { label: 'متصل', color: 'text-green-400', bg: 'bg-green-500/10 border-green-500/30' }
      case 'connecting': return { label: 'جارٍ الاتصال...', color: 'text-yellow-400', bg: 'bg-yellow-500/10 border-yellow-500/30' }
      case 'qr_needed': return { label: 'يحتاج QR', color: 'text-gray-400', bg: 'bg-gray-500/10 border-gray-500/30' }
      default: return { label: 'غير متصل', color: 'text-red-400', bg: 'bg-red-500/10 border-red-500/30' }
    }
  }

  return (
    <div className="space-y-5">
      {qrModal && (
        <QrModal instanceId={qrModal.id} initialMode={qrModal.mode} onClose={() => setQrModal(null)} onConnected={refresh} />
      )}
      {deleteTarget && (
        <DeleteConfirmModal instance={deleteTarget} onClose={() => setDeleteTarget(null)} onDeleted={() => mutate()} />
      )}
      {addModal && (
        <AddInstanceModal onClose={() => setAddModal(false)} onAdded={() => mutate()} />
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white font-cairo">أرقام واتساب</h1>
          <p className="text-gray-400 text-sm mt-1 font-cairo">
            الأرقام التي ترسل منها حملاتك وتستقبل عليها الردود. الرقم الجديد يرد فقط أول {QUIET_DAYS} يوماً لحمايته من الحظر.
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          <button
            onClick={refresh}
            className="flex items-center gap-1.5 text-gray-400 hover:text-white text-sm px-3 py-2 rounded-lg border border-gray-700 hover:border-gray-600 transition-colors"
          >
            <RefreshCw size={14} />
            <span className="font-cairo">تحديث</span>
          </button>
          <button
            onClick={() => setAddModal(true)}
            className="flex items-center gap-2 bg-gradient-to-r from-gold-primary to-gold-dark text-gray-950 font-semibold text-sm px-4 py-2 rounded-lg hover:opacity-90 transition-all font-cairo"
          >
            <Plus size={16} />
            إضافة رقم
          </button>
        </div>
      </div>

      {/* Warning banner */}
      {Object.values(health).some((n) => n.state === 'disconnected') && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl px-4 py-3 flex items-center gap-3">
          <AlertTriangle size={18} className="text-red-400 shrink-0" />
          <p className="text-sm text-red-300 font-cairo">
            رقم أو أكثر غير متصل — لن يرسل أو يستقبل حتى تعيد ربطه. استخدم زر «إعادة الربط» في البطاقة.
          </p>
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-16">
          <div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" />
        </div>
      ) : instances.length === 0 ? (
        <div className="text-center py-20 text-gray-600">
          <QrCode size={48} className="mx-auto mb-3 text-gray-700" />
          <p className="font-cairo text-gray-300">لم تربط أي رقم واتساب بعد</p>
          <p className="text-sm text-gray-500 mt-1 mb-4 font-cairo">اربط رقماً لتبدأ استقبال الرسائل؛ تبدأ الحملات منه بعد فترة الحماية.</p>
          <button
            onClick={() => setAddModal(true)}
            className="bg-gradient-to-r from-gold-primary to-gold-dark text-gray-950 font-semibold px-5 py-2.5 rounded-lg hover:opacity-90 transition-all font-cairo"
          >
            ربط أول رقم
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {instances.map((inst) => {
            const statusCfg = getStatusConfig(inst.status)
            const h = health[inst.id]
            const st = h ? NUMBER_STATE[h.state] : null
            const linked = h ? h.state !== 'disconnected' : (inst.status === 'connected' || inst.status === 'open')
            // Progress toward full sending: protection (days 0-13) → reduced (14-20) → full (21+).
            const ageProgress = h ? Math.min(100, (h.day / FULL_DAYS) * 100) : 0
            return (
              <div
                key={inst.id}
                className={clsx('bg-gray-900 border rounded-xl p-5 space-y-4 transition-colors',
                  linked ? 'border-gray-800 hover:border-gray-700' : 'border-red-500/30')}
              >
                {/* Header */}
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3 className="font-semibold text-white font-cairo truncate">
                      {inst.display_name || inst.instance_name}
                    </h3>
                    <p className="text-sm text-gray-500" dir="ltr">{inst.phone_number || 'لم يُربط بعد'}</p>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <span className={clsx('text-xs px-2 py-1 rounded-lg border font-cairo font-semibold',
                      st ? st.tone : clsx(statusCfg.bg, statusCfg.color))}>
                      {st ? st.label : statusCfg.label}
                    </span>
                    <button
                      onClick={() => setDeleteTarget(inst)}
                      className="text-gray-600 hover:text-red-400 p-1 rounded transition-colors"
                      title="حذف الرقم" aria-label="حذف الرقم"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                {h && st && <p className="text-xs text-gray-400 font-cairo leading-relaxed">{st.hint(h)}</p>}

                {/* Health: today's campaign sending + progress toward the full daily limit */}
                {h && linked && (
                  <div className="bg-gray-800/50 rounded-lg p-3 space-y-2.5 text-xs font-cairo">
                    <div className="flex justify-between text-gray-400">
                      <span>حملات اليوم</span>
                      <span className="text-gray-200 tabular-nums">
                        {h.daily_limit > 0 ? `${h.sent_today} / ${h.daily_limit}` : 'لا إرسال حملات اليوم'}
                      </span>
                    </div>
                    {h.daily_limit > 0 && (
                      <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                        <div className="h-full bg-wa-green rounded-full" style={{ width: `${Math.min(100, (h.sent_today / h.daily_limit) * 100)}%` }} />
                      </div>
                    )}
                    {h.day < FULL_DAYS && (
                      <>
                        <div className="flex justify-between text-gray-400">
                          <span>عمر الرقم</span>
                          <span className="text-gray-200">اليوم {h.day} من {FULL_DAYS}</span>
                        </div>
                        <div className="relative h-1.5 bg-gray-700 rounded-full overflow-hidden">
                          <div className="h-full bg-amber-400/80 rounded-full" style={{ width: `${ageProgress}%` }} />
                          <span className="absolute top-0 h-full w-px bg-gray-300" style={{ insetInlineStart: `${(QUIET_DAYS / FULL_DAYS) * 100}%` }} />
                        </div>
                      </>
                    )}
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-2">
                  {!linked && (
                    <button
                      onClick={() => setQrModal({ id: inst.id, mode: inst.status === 'disconnected' ? 'phone' : 'qr' })}
                      className="flex-1 flex items-center justify-center gap-1.5 bg-gold-primary text-gray-950 hover:opacity-90 rounded-lg py-2 text-sm font-semibold transition-opacity font-cairo"
                    >
                      <Wifi size={14} />
                      {inst.status === 'disconnected' ? 'إعادة الربط' : 'إكمال الربط'}
                    </button>
                  )}
                  {linked && (
                    <button
                      onClick={() => handleSync(inst.id)}
                      title="استيراد المحادثات السابقة من واتساب"
                      className="flex-1 flex items-center justify-center gap-1.5 bg-gray-500/10 hover:bg-gray-500/20 text-gray-400 border border-gray-500/30 rounded-lg py-2 text-xs font-semibold transition-colors font-cairo"
                    >
                      <Download size={13} />مزامنة المحادثات
                    </button>
                  )}
                  {/* Pause/resume — the safe daily control: stops sending, keeps the session. */}
                  {linked && (
                    <button
                      onClick={async () => { await handlePause(inst.id, !inst.paused); mutateHome() }}
                      className={clsx(
                        'flex-1 flex items-center justify-center gap-1.5 rounded-lg py-2 text-xs font-semibold transition-colors font-cairo border',
                        inst.paused
                          ? 'bg-green-500/10 hover:bg-green-500/20 text-green-400 border-green-500/30'
                          : 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border-amber-500/30'
                      )}
                    >
                      {inst.paused ? <><Play size={13} />استئناف الحملات</> : <><Pause size={13} />إيقاف الحملات</>}
                    </button>
                  )}
                  {/* Disconnect — demoted: real logout, gated behind a confirm. */}
                  {linked && (
                    <button
                      onClick={() => handleDisconnect(inst.id)}
                      title="تسجيل خروج الرقم من واتساب (يتطلب إعادة الربط)"
                      aria-label="تسجيل خروج الرقم"
                      className="shrink-0 flex items-center justify-center gap-1.5 bg-gray-800 hover:bg-red-500/10 text-gray-400 hover:text-red-400 border border-gray-700 hover:border-red-500/30 rounded-lg py-2 px-2.5 text-xs font-semibold transition-colors font-cairo"
                    >
                      <WifiOff size={13} />
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
