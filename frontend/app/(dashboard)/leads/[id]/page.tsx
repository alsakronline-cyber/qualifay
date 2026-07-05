'use client'

import { useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import {
  ArrowRight,
  Building2,
  Phone,
  Mail,
  Globe,
  MapPin,
  Briefcase,
  User,
  CheckCircle,
  XCircle,
  UserCheck,
  Save,
} from 'lucide-react'
import Link from 'next/link'
import { leadsApi } from '@/lib/api'
import type { Lead } from '@/lib/types'
import ActivityFeed from '@/components/activity-feed'

import { PIPELINE_STAGES, STAGE_LABELS } from '@/lib/stages'

const STAGE_COLORS: Record<string, string> = {
  new: 'text-blue-400 bg-blue-500/10',
  qualifying: 'text-blue-400 bg-blue-500/10',
  pending_review: 'text-yellow-400 bg-yellow-500/10',
  approved: 'text-green-400 bg-green-500/10',
  manual: 'text-purple-400 bg-purple-500/10',
  outreach: 'text-cyan-400 bg-cyan-500/10',
  replied: 'text-teal-400 bg-teal-500/10',
  meeting: 'text-cyan-400 bg-cyan-500/10',
  proposal: 'text-purple-400 bg-purple-500/10',
  negotiation: 'text-orange-400 bg-orange-500/10',
  won: 'text-emerald-400 bg-emerald-500/10',
  lost: 'text-gray-400 bg-gray-700',
  archived: 'text-gray-500 bg-gray-800',
}

function BANTBadge({ score }: { score?: number }) {
  if (score === undefined) return null
  const color = score >= 70 ? 'text-green-400 bg-green-500/10 border-green-500/30'
    : score >= 50 ? 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30'
    : 'text-red-400 bg-red-500/10 border-red-500/30'
  return (
    <span className={clsx('inline-flex items-center gap-1 text-sm font-bold px-2.5 py-1 rounded-lg border', color)}>
      BANT {score}
    </span>
  )
}

export default function LeadDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()

  const { data, mutate, isLoading } = useSWR(
    id ? `leads/${id}` : null,
    () => leadsApi.getOne(id).then((r) => r.data)
  )
  const lead: Lead | undefined = data

  // Editable form state (synced from lead on load)
  const [form, setForm] = useState<Partial<Lead>>({})
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)

  // When lead loads, seed form
  const seedForm = useCallback((l: Lead) => {
    setForm({
      name: l.name || '',
      company: l.company || '',
      phone: l.phone || '',
      email: l.email || '',
      industry: l.industry || '',
      city: l.city || '',
      website: l.website || '',
      ai_notes: l.ai_notes || '',
    })
    setDirty(false)
  }, [])

  // Seed once when lead arrives
  const [seeded, setSeeded] = useState(false)
  if (lead && !seeded) {
    seedForm(lead)
    setSeeded(true)
  }

  const handleChange = (field: keyof Lead, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }))
    setDirty(true)
  }

  const handleSave = useCallback(async () => {
    if (!id || !dirty) return
    setSaving(true)
    try {
      await leadsApi.update(id, form as Record<string, unknown>)
      toast.success('تم حفظ التغييرات')
      setDirty(false)
      mutate()
    } catch {
      toast.error('فشل حفظ التغييرات')
    } finally {
      setSaving(false)
    }
  }, [id, dirty, form, mutate])

  const handleApprove = useCallback(async () => {
    if (!id) return
    try {
      await leadsApi.approve(id)
      toast.success('تم قبول العميل المحتمل')
      mutate()
    } catch {
      toast.error('فشل القبول')
    }
  }, [id, mutate])

  const handleReject = useCallback(async () => {
    if (!id) return
    try {
      await leadsApi.reject(id)
      toast.success('تم رفض العميل المحتمل')
      mutate()
    } catch {
      toast.error('فشل الرفض')
    }
  }, [id, mutate])

  const handleTakeManually = useCallback(async () => {
    if (!id) return
    try {
      await leadsApi.takeManually(id)
      toast.success('تم نقل العميل للمعالجة اليدوية')
      mutate()
    } catch {
      toast.error('فشل العملية')
    }
  }, [id, mutate])

  const handleSetStage = useCallback(async (stage: string) => {
    if (!id) return
    try {
      await leadsApi.updateStage(id, stage)
      toast.success('تم تحديث المرحلة')
      mutate()
    } catch {
      toast.error('فشل تحديث المرحلة')
    }
  }, [id, mutate])

  if (isLoading) {
    return (
      <div className="flex justify-center py-20">
        <div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (!lead) {
    return (
      <div className="text-center py-20 text-gray-500 font-cairo">
        العميل غير موجود
      </div>
    )
  }

  return (
    <div className="space-y-5 max-w-6xl">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-gray-400">
        <Link href="/leads" className="hover:text-white transition-colors font-cairo flex items-center gap-1">
          <ArrowRight size={14} />
          العملاء المحتملون
        </Link>
        <span>/</span>
        <span className="text-gray-200 font-cairo">{lead.company || lead.name || id}</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Main column */}
        <div className="lg:col-span-2 space-y-5">
          {/* Header card */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
            <div className="flex items-start justify-between flex-wrap gap-3">
              <div>
                <h1 className="text-xl font-bold text-white font-cairo">{lead.company || lead.name || '—'}</h1>
                <p className="text-gray-400 text-sm font-cairo mt-0.5">{lead.industry} · {lead.city}</p>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <BANTBadge score={lead.bant_score} />
                {/* Stage picker — lets the user place this lead in the right pipeline phase. */}
                <select
                  value={PIPELINE_STAGES.some((s) => s.value === lead.stage) ? lead.stage : ''}
                  onChange={(e) => handleSetStage(e.target.value)}
                  className={clsx(
                    'text-xs font-semibold px-2.5 py-1 rounded-lg font-cairo border-0 focus:outline-none focus:ring-1 focus:ring-gold-primary cursor-pointer',
                    STAGE_COLORS[lead.stage || ''] || 'text-gray-400 bg-gray-700'
                  )}
                >
                  {/* Current non-pipeline stage (e.g. pending_review) shown as a disabled hint. */}
                  {!PIPELINE_STAGES.some((s) => s.value === lead.stage) && (
                    <option value="" disabled>{STAGE_LABELS[lead.stage || ''] || lead.stage || 'اختر مرحلة'}</option>
                  )}
                  {PIPELINE_STAGES.map((s) => (
                    <option key={s.value} value={s.value} className="bg-gray-900 text-white">{s.label}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* BANT breakdown */}
            {(lead.bant_budget !== undefined || lead.bant_authority !== undefined) && (
              <div className="mt-4 grid grid-cols-4 gap-3">
                {(['budget', 'authority', 'need', 'timeline'] as const).map((dim) => {
                  const key = `bant_${dim}` as keyof Lead
                  const val = lead[key] as number | undefined
                  const labels: Record<string, string> = { budget: 'الميزانية', authority: 'الصلاحية', need: 'الحاجة', timeline: 'الجدول' }
                  return (
                    <div key={dim} className="bg-gray-800/50 rounded-lg p-3 text-center">
                      <div className={clsx(
                        'text-lg font-bold',
                        val !== undefined && val >= 70 ? 'text-green-400' : val !== undefined && val >= 50 ? 'text-yellow-400' : 'text-red-400'
                      )}>
                        {val ?? '—'}
                      </div>
                      <div className="text-xs text-gray-500 font-cairo mt-0.5">{labels[dim]}</div>
                    </div>
                  )
                })}
              </div>
            )}

            {lead.bant_reason && (
              <div className="mt-3 p-3 bg-gray-800/50 rounded-lg">
                <p className="text-xs text-gray-400 font-cairo leading-relaxed">{lead.bant_reason}</p>
              </div>
            )}
          </div>

          {/* Edit form */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-white font-cairo mb-4 flex items-center gap-2">
              <User size={14} className="text-gray-400" />
              بيانات العميل
              <span className="text-xs text-gray-500 font-normal">Contact Details</span>
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field
                icon={<User size={13} />}
                label="الاسم / Name"
                value={form.name || ''}
                onChange={(v) => handleChange('name', v)}
              />
              <Field
                icon={<Building2 size={13} />}
                label="الشركة / Company"
                value={form.company || ''}
                onChange={(v) => handleChange('company', v)}
              />
              <Field
                icon={<Phone size={13} />}
                label="الهاتف / Phone"
                value={form.phone || ''}
                onChange={(v) => handleChange('phone', v)}
                dir="ltr"
              />
              <Field
                icon={<Mail size={13} />}
                label="البريد الإلكتروني / Email"
                value={form.email || ''}
                onChange={(v) => handleChange('email', v)}
                dir="ltr"
              />
              <Field
                icon={<Briefcase size={13} />}
                label="المجال / Industry"
                value={form.industry || ''}
                onChange={(v) => handleChange('industry', v)}
              />
              <Field
                icon={<MapPin size={13} />}
                label="المدينة / City"
                value={form.city || ''}
                onChange={(v) => handleChange('city', v)}
              />
              <div className="sm:col-span-2">
                <Field
                  icon={<Globe size={13} />}
                  label="الموقع الإلكتروني / Website"
                  value={form.website || ''}
                  onChange={(v) => handleChange('website', v)}
                  dir="ltr"
                />
              </div>
              <div className="sm:col-span-2">
                <label className="block text-xs text-gray-400 font-cairo mb-1.5">ملاحظات / Notes</label>
                <textarea
                  value={form.ai_notes || ''}
                  onChange={(e) => handleChange('ai_notes', e.target.value)}
                  rows={3}
                  dir="rtl"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo resize-none"
                  placeholder="ملاحظات إضافية..."
                />
              </div>
            </div>

            <div className="flex items-center gap-2 mt-5 pt-4 border-t border-gray-800 flex-wrap">
              <button
                onClick={handleSave}
                disabled={!dirty || saving}
                className="flex items-center gap-1.5 bg-gold-primary hover:bg-gold-dark disabled:opacity-40 text-gray-950 font-semibold text-sm px-4 py-2 rounded-lg transition-colors font-cairo"
              >
                {saving ? (
                  <span className="w-3.5 h-3.5 border-2 border-gray-950 border-t-transparent rounded-full animate-spin" />
                ) : (
                  <Save size={13} />
                )}
                حفظ التغييرات
              </button>

              {lead.stage === 'pending_review' && (
                <>
                  <button
                    onClick={handleApprove}
                    className="flex items-center gap-1.5 bg-green-500/10 hover:bg-green-500/20 text-green-400 border border-green-500/30 text-sm px-4 py-2 rounded-lg transition-colors font-cairo"
                  >
                    <CheckCircle size={13} />
                    قبول للتواصل
                  </button>
                  <button
                    onClick={handleReject}
                    className="flex items-center gap-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 text-sm px-4 py-2 rounded-lg transition-colors font-cairo"
                  >
                    <XCircle size={13} />
                    رفض
                  </button>
                  <button
                    onClick={handleTakeManually}
                    className="flex items-center gap-1.5 bg-purple-500/10 hover:bg-purple-500/20 text-purple-400 border border-purple-500/30 text-sm px-4 py-2 rounded-lg transition-colors font-cairo"
                  >
                    <UserCheck size={13} />
                    استلام يدوي
                  </button>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Activity column */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 h-fit">
          <ActivityFeed entityId={id} entityType="lead" />
        </div>
      </div>
    </div>
  )
}

// Reusable field component
function Field({
  icon, label, value, onChange, dir,
}: {
  icon: React.ReactNode
  label: string
  value: string
  onChange: (v: string) => void
  dir?: 'ltr' | 'rtl'
}) {
  return (
    <div>
      <label className="flex items-center gap-1.5 text-xs text-gray-400 font-cairo mb-1.5">
        <span className="text-gray-500">{icon}</span>
        {label}
      </label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        dir={dir || 'rtl'}
        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo"
      />
    </div>
  )
}
