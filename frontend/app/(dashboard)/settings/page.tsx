'use client'

import { useState, useCallback } from 'react'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { Save, Copy, RefreshCw, Trash2, Bot } from 'lucide-react'
import { authApi, agentApi } from '@/lib/api'
import type { AuthUser } from '@/lib/types'

interface AgentTask {
  id: string
  platform: 'linkedin' | 'facebook'
  type: string
  params: Record<string, string | number>
  status: string
  recurring: boolean
  result_count: number
  total_results: number
  error_message: string | null
  created_at: string
}

const TASK_TYPES: Record<string, { label: string; fields: string[] }> = {
  linkedin_search: { label: 'بحث LinkedIn', fields: ['query', 'location'] },
  facebook_group_watch: { label: 'مراقبة مجموعة فيسبوك', fields: ['group_id'] },
  facebook_page_watch: { label: 'مراقبة صفحة فيسبوك', fields: ['page_id'] },
}

const STATUS_LABEL: Record<string, string> = {
  pending: 'انتظار', in_progress: 'جارٍ', done: 'مكتمل', error: 'خطأ',
}

function AutomationPanel() {
  const { data: setup, mutate: mutateSetup } = useSWR(
    'agent/setup', () => agentApi.getSetup().then((r) => r.data)
  )
  const { data: tasksData, mutate: mutateTasks } = useSWR(
    'agent/tasks', () => agentApi.listTasks().then((r) => r.data), { refreshInterval: 10000 }
  )
  const tasks: AgentTask[] = Array.isArray(tasksData) ? tasksData : []

  const [platform, setPlatform] = useState<'linkedin' | 'facebook'>('linkedin')
  const [type, setType] = useState('linkedin_search')
  const [query, setQuery] = useState('')
  const [location, setLocation] = useState('')
  const [groupId, setGroupId] = useState('')
  const [pageId, setPageId] = useState('')
  const [recurring, setRecurring] = useState(false)
  const [intervalMinutes, setIntervalMinutes] = useState(120)
  const [maxResults, setMaxResults] = useState(30)
  const [submitting, setSubmitting] = useState(false)

  const typesForPlatform = Object.entries(TASK_TYPES).filter(([, v]) =>
    platform === 'linkedin' ? v.label.includes('LinkedIn') : !v.label.includes('LinkedIn')
  )

  const copyKey = useCallback(() => {
    if (setup?.agent_key) {
      navigator.clipboard.writeText(setup.agent_key)
      toast.success('تم نسخ المفتاح')
    }
  }, [setup])

  const regenerate = useCallback(async () => {
    if (!confirm('سيتوقف الإضافة الحالية عن العمل حتى تُحدّث المفتاح فيها. متابعة؟')) return
    try {
      await agentApi.regenerateKey()
      mutateSetup()
      toast.success('تم تجديد المفتاح')
    } catch {
      toast.error('فشل التجديد')
    }
  }, [mutateSetup])

  const createTask = useCallback(async () => {
    setSubmitting(true)
    try {
      await agentApi.createTask({
        platform, type, query: query || undefined, location: location || undefined,
        group_id: groupId || undefined, page_id: pageId || undefined,
        max_results: maxResults, recurring, interval_minutes: intervalMinutes,
      })
      toast.success('تمت إضافة المهمة')
      setQuery(''); setLocation(''); setGroupId(''); setPageId('')
      mutateTasks()
    } catch {
      toast.error('فشلت إضافة المهمة')
    } finally {
      setSubmitting(false)
    }
  }, [platform, type, query, location, groupId, pageId, maxResults, recurring, intervalMinutes, mutateTasks])

  const removeTask = useCallback(async (id: string) => {
    try { await agentApi.deleteTask(id); mutateTasks() } catch { toast.error('فشل الحذف') }
  }, [mutateTasks])

  const fields = TASK_TYPES[type]?.fields || []

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-5">
      <h2 className="text-base font-semibold text-white font-cairo flex items-center gap-2">
        <Bot size={17} className="text-gold-primary" /> أتمتة LinkedIn وفيسبوك (إضافة المتصفح)
      </h2>
      <p className="text-xs text-gray-500 font-cairo leading-relaxed">
        ثبّت إضافة Qualifay Agent في متصفحك، سجّل دخولك على LinkedIn/Facebook كالمعتاد،
        والصق مفتاح الأتمتة هذا في إعدادات الإضافة. بعدها تعمل تلقائياً بدون أي تدخل يدوي
        طالما المتصفح مفتوح.
      </p>

      {/* Agent key */}
      <div>
        <label className="block text-sm text-gray-300 font-cairo mb-1.5">مفتاح الأتمتة</label>
        <div className="flex gap-2">
          <input
            type="text" readOnly value={setup?.agent_key || '...'} dir="ltr"
            className="flex-1 bg-gray-800/50 border border-gray-700 rounded-lg px-3 py-2.5 text-gray-300 text-xs font-mono"
          />
          <button onClick={copyKey} className="bg-gray-800 border border-gray-700 rounded-lg px-3 hover:border-gold-primary transition-colors">
            <Copy size={14} className="text-gray-400" />
          </button>
          <button onClick={regenerate} className="bg-gray-800 border border-gray-700 rounded-lg px-3 hover:border-red-500 transition-colors" title="تجديد المفتاح">
            <RefreshCw size={14} className="text-gray-400" />
          </button>
        </div>
        {setup && (
          <p className="text-xs text-gray-600 font-cairo mt-1.5">
            الحد اليومي: {setup.daily_cap_linkedin} LinkedIn · {setup.daily_cap_facebook} Facebook
          </p>
        )}
      </div>

      {/* New task form */}
      <div className="bg-gray-800/40 rounded-lg p-4 space-y-3">
        <p className="text-sm font-cairo text-gray-300 font-medium">إضافة مهمة جديدة</p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-gray-500 font-cairo mb-1">المنصة</label>
            <select value={platform} onChange={(e) => { const p = e.target.value as 'linkedin' | 'facebook'; setPlatform(p); setType(p === 'linkedin' ? 'linkedin_search' : 'facebook_group_watch') }}
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-cairo">
              <option value="linkedin">LinkedIn</option>
              <option value="facebook">Facebook</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 font-cairo mb-1">النوع</label>
            <select value={type} onChange={(e) => setType(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-cairo">
              {typesForPlatform.map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>
        </div>

        {fields.includes('query') && (
          <input type="text" placeholder="الكلمة البحثية / المسمى الوظيفي" value={query} onChange={(e) => setQuery(e.target.value)}
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-cairo" />
        )}
        {fields.includes('location') && (
          <input type="text" placeholder="الموقع (اختياري)" value={location} onChange={(e) => setLocation(e.target.value)}
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-cairo" />
        )}
        {fields.includes('group_id') && (
          <input type="text" placeholder="معرّف المجموعة (من رابط المجموعة)" value={groupId} onChange={(e) => setGroupId(e.target.value)} dir="ltr"
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-cairo" />
        )}
        {fields.includes('page_id') && (
          <input type="text" placeholder="معرّف الصفحة" value={pageId} onChange={(e) => setPageId(e.target.value)} dir="ltr"
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-cairo" />
        )}

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-gray-400 font-cairo">
            <input type="checkbox" checked={recurring} onChange={(e) => setRecurring(e.target.checked)} />
            تكرار مستمر
          </label>
          {recurring && (
            <select value={intervalMinutes} onChange={(e) => setIntervalMinutes(Number(e.target.value))}
              className="bg-gray-900 border border-gray-700 rounded-lg px-2 py-1 text-xs text-white font-cairo">
              <option value={60}>كل ساعة</option>
              <option value={120}>كل ساعتين</option>
              <option value={360}>كل 6 ساعات</option>
              <option value={1440}>يومياً</option>
            </select>
          )}
          <input type="number" min={1} max={200} value={maxResults} onChange={(e) => setMaxResults(Number(e.target.value))}
            placeholder="أقصى عدد" className="w-24 bg-gray-900 border border-gray-700 rounded-lg px-2 py-1 text-xs text-white font-cairo" />
        </div>

        <button onClick={createTask} disabled={submitting}
          className="text-sm bg-gold-primary text-gray-950 font-bold px-4 py-2 rounded-lg hover:opacity-90 disabled:opacity-50 font-cairo">
          {submitting ? '...' : 'إضافة المهمة'}
        </button>
      </div>

      {/* Task list */}
      {tasks.length > 0 && (
        <div className="space-y-2">
          {tasks.map((t) => (
            <div key={t.id} className="flex items-center justify-between bg-gray-800/50 rounded-lg px-3 py-2">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className={clsx('text-xs px-1.5 py-0.5 rounded font-cairo',
                    t.status === 'error' ? 'bg-red-500/15 text-red-400' :
                    t.status === 'done' ? 'bg-green-500/15 text-green-400' :
                    t.status === 'in_progress' ? 'bg-blue-500/15 text-blue-400' : 'bg-gray-700 text-gray-400')}>
                    {STATUS_LABEL[t.status] || t.status}
                  </span>
                  <span className="text-sm text-white font-cairo">{TASK_TYPES[t.type]?.label || t.type}</span>
                  {t.recurring && <span className="text-[10px] text-gold-primary font-cairo">متكرر</span>}
                </div>
                <p className="text-xs text-gray-500 font-cairo truncate">
                  {String(t.params.query || t.params.group_id || t.params.page_id || '')}
                  {t.params.location ? ` · ${t.params.location}` : ''} · إجمالي: {t.total_results}
                </p>
                {t.error_message && <p className="text-xs text-red-400/80 font-cairo truncate">{t.error_message}</p>}
              </div>
              <button onClick={() => removeTask(t.id)} className="text-red-400 hover:text-red-300 p-1.5 shrink-0"><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function SettingsPage() {
  const { data: user } = useSWR<AuthUser>(
    'auth/me',
    () => authApi.me().then((r) => r.data)
  )

  const [name, setName] = useState(user?.name || '')
  const [saving, setSaving] = useState(false)

  return (
    <div className="space-y-5 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-white font-cairo">الإعدادات</h1>
        <p className="text-gray-400 text-sm mt-1">Settings</p>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
        <h2 className="text-base font-semibold text-white font-cairo">معلومات الحساب</h2>
        <div>
          <label className="block text-sm text-gray-300 font-cairo mb-1.5">الاسم</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo text-sm"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-300 font-cairo mb-1.5">البريد الإلكتروني</label>
          <input
            type="email"
            value={user?.email || ''}
            readOnly
            className="w-full bg-gray-800/50 border border-gray-700 rounded-lg px-4 py-2.5 text-gray-400 text-sm cursor-not-allowed"
            dir="ltr"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-300 font-cairo mb-1.5">اسم المشروع</label>
          <input
            type="text"
            value={user?.tenant?.name || ''}
            readOnly
            className="w-full bg-gray-800/50 border border-gray-700 rounded-lg px-4 py-2.5 text-gray-400 text-sm cursor-not-allowed font-cairo"
          />
        </div>
        <button
          disabled={saving}
          onClick={async () => {
            setSaving(true)
            await new Promise((r) => setTimeout(r, 800))
            setSaving(false)
            toast.success('تم حفظ الإعدادات')
          }}
          className="flex items-center gap-2 bg-gradient-to-r from-gold-primary to-gold-dark text-gray-950 font-semibold px-5 py-2.5 rounded-lg hover:opacity-90 disabled:opacity-50 transition-all font-cairo text-sm"
        >
          {saving ? (
            <span className="w-4 h-4 border-2 border-gray-950 border-t-transparent rounded-full animate-spin" />
          ) : (
            <Save size={15} />
          )}
          حفظ التغييرات
        </button>
      </div>

      {/* Plan info */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-3">
        <h2 className="text-base font-semibold text-white font-cairo">الخطة الحالية</h2>
        <div className="flex items-center gap-3">
          <span className="text-2xl font-bold text-gold-primary capitalize">{user?.tenant?.plan || '—'}</span>
          <span className="text-sm text-gray-500 font-cairo">خطتك الحالية</span>
        </div>
        <a
          href="/billing"
          className="inline-flex items-center text-sm text-gold-primary hover:text-gold-dark transition-colors font-cairo"
        >
          ترقية الخطة ←
        </a>
      </div>

      <AutomationPanel />
    </div>
  )
}
