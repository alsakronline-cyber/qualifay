'use client'

import { useState, useCallback } from 'react'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { Plus, QrCode, RefreshCw, Wifi, WifiOff, AlertTriangle, X, Trash2, Download, Pause, Play } from 'lucide-react'
import { instancesApi } from '@/lib/api'
import type { WaInstance } from '@/lib/types'
import WarmupIndicator from '@/components/WarmupIndicator'

function QrModal({ instanceId, onClose }: { instanceId: string; onClose: () => void }) {
  const { data, isLoading, error } = useSWR(
    `instances/${instanceId}/qr`,
    () => instancesApi.getQr(instanceId).then((r) => r.data),
    { refreshInterval: 3000 }
  )

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 w-full max-w-sm relative">
        <button
          onClick={onClose}
          className="absolute top-4 left-4 text-gray-400 hover:text-white"
        >
          <X size={18} />
        </button>
        <h3 className="text-lg font-semibold text-white font-cairo text-center mb-4">
          امسح رمز QR للاتصال
        </h3>
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

  const [qrModalId, setQrModalId] = useState<string | null>(null)
  const [addModal, setAddModal] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<WaInstance | null>(null)

  const handleReconnect = useCallback(async (id: string) => {
    try {
      await instancesApi.reconnect(id)
      toast.success('جارٍ إعادة الاتصال...')
      setTimeout(() => mutate(), 3000)
    } catch {
      toast.error('فشل إعادة الاتصال')
    }
  }, [mutate])

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
    if (!confirm('قطع الاتصال يسجّل خروج الرقم من واتساب — ستحتاج إلى مسح رمز QR لإعادة الربط. للإيقاف المؤقت للإرسال دون فقد الجلسة استخدم "إيقاف مؤقت". متابعة؟')) return
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
      case 'qr_needed': return { label: 'يحتاج QR', color: 'text-orange-400', bg: 'bg-orange-500/10 border-orange-500/30' }
      default: return { label: 'غير متصل', color: 'text-red-400', bg: 'bg-red-500/10 border-red-500/30' }
    }
  }

  return (
    <div className="space-y-5">
      {qrModalId && (
        <QrModal instanceId={qrModalId} onClose={() => setQrModalId(null)} />
      )}
      {deleteTarget && (
        <DeleteConfirmModal instance={deleteTarget} onClose={() => setDeleteTarget(null)} onDeleted={() => mutate()} />
      )}
      {addModal && (
        <AddInstanceModal onClose={() => setAddModal(false)} onAdded={() => mutate()} />
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white font-cairo">نسخ واتساب</h1>
          <p className="text-gray-400 text-sm mt-1">WhatsApp Instances</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => mutate()}
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
            إضافة نسخة
          </button>
        </div>
      </div>

      {/* Warning banner */}
      {instances.some((i) => i.sent_today_wa >= i.daily_wa_cap * 0.9) && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl px-4 py-3 flex items-center gap-3">
          <AlertTriangle size={18} className="text-yellow-400 shrink-0" />
          <p className="text-sm text-yellow-300 font-cairo">
            بعض النسخ اقتربت من الحد اليومي. تحقق من مؤشرات الإحماء أدناه.
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
          <p className="font-cairo">لا توجد نسخ واتساب بعد</p>
          <p className="text-sm text-gray-700 mt-1 mb-4">No WhatsApp instances yet</p>
          <button
            onClick={() => setAddModal(true)}
            className="bg-gradient-to-r from-gold-primary to-gold-dark text-gray-950 font-semibold px-5 py-2.5 rounded-lg hover:opacity-90 transition-all font-cairo"
          >
            إضافة أول نسخة
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {instances.map((inst) => {
            const statusCfg = getStatusConfig(inst.status)
            const usageRatio = inst.daily_wa_cap > 0 ? inst.sent_today_wa / inst.daily_wa_cap : 0
            return (
              <div
                key={inst.id}
                className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4 hover:border-gray-700 transition-colors"
              >
                {/* Header */}
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-semibold text-white font-cairo">
                      {inst.display_name || inst.instance_name}
                    </h3>
                    <p className="text-sm text-gray-500">{inst.phone_number || 'لم يُربط بعد'}</p>
                  </div>
                  <span className={clsx('text-xs px-2 py-1 rounded-lg border font-cairo font-semibold', statusCfg.bg, statusCfg.color)}>
                    {statusCfg.label}
                  </span>
                  <button
                    onClick={() => setDeleteTarget(inst)}
                    className="text-gray-600 hover:text-red-400 p-1 rounded transition-colors"
                    title="حذف النسخة"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>

                {/* Warmup indicator */}
                <WarmupIndicator instance={inst} />

                {/* Actions */}
                <div className="flex gap-2">
                  {(inst.status === 'disconnected' || inst.status === 'qr_needed' || inst.status === 'connecting') && (
                    <button
                      onClick={() => setQrModalId(inst.id)}
                      className="flex-1 flex items-center justify-center gap-1.5 bg-gold-primary/10 hover:bg-gold-primary/20 text-gold-primary border border-gold-primary/30 rounded-lg py-2 text-xs font-semibold transition-colors font-cairo"
                    >
                      <QrCode size={13} />
                      ربط QR
                    </button>
                  )}
                  {inst.status === 'disconnected' && (
                    <button
                      onClick={() => handleReconnect(inst.id)}
                      className="flex-1 flex items-center justify-center gap-1.5 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded-lg py-2 text-xs font-semibold transition-colors font-cairo"
                    >
                      <Wifi size={13} />
                      إعادة اتصال
                    </button>
                  )}
                  {(inst.status === 'connected' || inst.status === 'open') && (
                    <button
                      onClick={() => handleSync(inst.id)}
                      className="flex-1 flex items-center justify-center gap-1.5 bg-purple-500/10 hover:bg-purple-500/20 text-purple-400 border border-purple-500/30 rounded-lg py-2 text-xs font-semibold transition-colors font-cairo"
                    >
                      <Download size={13} />مزامنة
                    </button>
                  )}
                  {/* Pause/resume — the safe daily control: stops sending, keeps the session. */}
                  {(inst.status === 'connected' || inst.status === 'open') && (
                    <button
                      onClick={() => handlePause(inst.id, !inst.paused)}
                      className={clsx(
                        'flex-1 flex items-center justify-center gap-1.5 rounded-lg py-2 text-xs font-semibold transition-colors font-cairo border',
                        inst.paused
                          ? 'bg-green-500/10 hover:bg-green-500/20 text-green-400 border-green-500/30'
                          : 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border-amber-500/30'
                      )}
                    >
                      {inst.paused ? <><Play size={13} />استئناف</> : <><Pause size={13} />إيقاف مؤقت</>}
                    </button>
                  )}
                  {/* Disconnect — demoted: real logout, gated behind a confirm. */}
                  {(inst.status === 'connected' || inst.status === 'open') && (
                    <button
                      onClick={() => handleDisconnect(inst.id)}
                      title="تسجيل خروج الرقم (يتطلب مسح QR لإعادة الربط)"
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
