'use client'

import { useState } from 'react'
import { clsx } from 'clsx'
import { CheckCircle, XCircle, UserCheck, ChevronDown, ChevronUp, Bot, MessageSquare, AlertTriangle } from 'lucide-react'
import type { Lead, LeadSource } from '@/lib/types'

interface LeadReviewCardProps {
  lead: Lead
  onApprove: (id: string, message?: string) => void
  onReject: (id: string, reason?: string) => void
  onTakeManually: (id: string) => void
  selected?: boolean
  onToggleSelect?: (id: string) => void
}

// One-tap reasons — rejection feedback is stored to improve future scoring, so make it easy.
const REJECT_REASONS = ['غير مناسب لنشاطنا', 'بيانات غير صحيحة', 'منافس', 'عميل حالي / مكرر']

const sourceLabels: Record<LeadSource, string> = {
  google_maps: 'خرائط جوجل',
  websites: 'مواقع',
  directories: 'أدلة',
  tenders: 'مناقصات',
  apollo: 'Apollo',
  linkedin: 'LinkedIn',
  facebook_groups: 'فيسبوك',
  enrichment: 'إثراء',
  competitor_ads: 'إعلانات',
  manual: 'يدوي',
  pool: 'المجمّع',
}

const sourceColors: Record<LeadSource, string> = {
  google_maps: 'bg-gray-500/10 text-gray-400',
  websites: 'bg-gray-500/10 text-gray-400',
  directories: 'bg-gray-500/10 text-gray-400',
  tenders: 'bg-gray-500/10 text-gray-400',
  apollo: 'bg-gray-500/10 text-gray-400',
  linkedin: 'bg-gray-500/10 text-gray-400',
  facebook_groups: 'bg-gray-600/10 text-gray-500',
  enrichment: 'bg-gray-500/10 text-gray-400',
  competitor_ads: 'bg-red-500/10 text-red-400',
  manual: 'bg-gray-500/10 text-gray-400',
  pool: 'bg-gold-primary/10 text-gold-primary',
}

function BANTBar({ label, value }: { label: string; value?: number }) {
  const pct = Math.min((value ?? 0) / 25, 1) * 100
  return (
    <div className="flex items-center gap-2">
      <span className="w-16 shrink-0 text-xs text-gray-400 font-cairo">{label}</span>
      <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
        <div
          className={clsx(
            'h-full rounded-full',
            pct >= 80 ? 'bg-green-500' : pct >= 50 ? 'bg-yellow-400' : 'bg-red-500'
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-6 text-right text-xs text-gray-400">{value ?? 0}</span>
    </div>
  )
}

export default function LeadReviewCard({
  lead,
  onApprove,
  onReject,
  onTakeManually,
  selected = false,
  onToggleSelect,
}: LeadReviewCardProps) {
  const [rejectMode, setRejectMode] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [expanded, setExpanded] = useState(false)
  const [loading, setLoading] = useState<'approve' | 'reject' | 'manual' | null>(null)
  const [draft, setDraft] = useState(lead.draft_message || '')
  const hasDraft = Boolean(lead.draft_message)

  const score = lead.bant_score ?? 0
  const scoreColor =
    score >= 70 ? 'text-green-400 bg-green-500/10 border-green-500/30'
    : score >= 50 ? 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30'
    : 'text-red-400 bg-red-500/10 border-red-500/30'

  async function handleApprove() {
    setLoading('approve')
    // In copilot mode the card carries an AI-drafted greeting; send the (edited) text.
    await onApprove(lead.id, hasDraft ? (draft.trim() || undefined) : undefined)
    setLoading(null)
  }

  async function handleReject(reason?: string) {
    if (!rejectMode && reason === undefined) { setRejectMode(true); return }
    setLoading('reject')
    await onReject(lead.id, (reason ?? rejectReason) || undefined)
    setLoading(null)
    setRejectMode(false)
    setRejectReason('')
  }

  async function handleManual() {
    setLoading('manual')
    await onTakeManually(lead.id)
    setLoading(null)
  }

  // Keyboard review: focus a card (Tab or click), then A = approve, R = reject, M = take manually.
  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.target !== e.currentTarget || loading) return
    const k = e.key.toLowerCase()
    if (k === 'a') { e.preventDefault(); handleApprove() }
    else if (k === 'r') { e.preventDefault(); handleReject() }
    else if (k === 'm') { e.preventDefault(); handleManual() }
  }

  const reach = [
    lead.phone && { label: 'واتساب', ok: true },
    lead.email && { label: 'بريد', ok: true },
  ].filter(Boolean) as { label: string; ok: boolean }[]

  return (
    <div
      tabIndex={0}
      onKeyDown={onKeyDown}
      aria-label={`مراجعة ${lead.company || lead.name || 'عميل'} — A قبول، R رفض، M يدوي`}
      className={clsx('bg-gray-900 border rounded-xl p-4 space-y-3 transition-colors focus:outline-none focus:ring-2 focus:ring-gold-primary/60',
        selected ? 'border-gold-primary/60' : 'border-gray-800 hover:border-gray-700')}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        {onToggleSelect && (
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onToggleSelect(lead.id)}
            aria-label="تحديد للقبول الجماعي"
            className="mt-1.5 w-4 h-4 accent-gold-primary shrink-0 cursor-pointer"
          />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-base font-semibold text-white font-cairo truncate">
              {lead.company || lead.name || 'غير محدد'}
            </h3>
            <span
              className={clsx(
                'text-xs px-2 py-0.5 rounded-full border',
                sourceColors[lead.source] || 'bg-gray-700 text-gray-400 border-gray-600'
              )}
            >
              {sourceLabels[lead.source] || lead.source}
            </span>
          </div>
          <div className="text-sm text-gray-400 mt-0.5 font-cairo">
            {[lead.industry, lead.city, lead.company_size].filter(Boolean).join(' · ')}
          </div>
          <div className="flex gap-1.5 mt-1.5">
            {reach.length ? reach.map((r) => (
              <span key={r.label} className="text-[11px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-300 font-cairo">✓ {r.label}</span>
            )) : <span className="text-[11px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 font-cairo">لا توجد وسيلة تواصل</span>}
          </div>
        </div>

        {/* BANT score circle */}
        <div
          className={clsx(
            'shrink-0 w-12 h-12 rounded-full border-2 flex items-center justify-center text-lg font-bold',
            scoreColor
          )}
        >
          {score}
        </div>
      </div>

      {/* Why this lead — the one line a reviewer actually needs */}
      {lead.bant_reason && (
        <div className="text-xs bg-gray-800/50 rounded-lg p-2.5 font-cairo leading-relaxed">
          <span className="text-gold-primary font-semibold">لماذا هذا العميل؟ </span>
          <span className="text-gray-300 line-clamp-3">{lead.bant_reason}</span>
        </div>
      )}

      {/* Score breakdown */}
      <div className="space-y-1.5">
        <BANTBar label="الميزانية" value={lead.bant_budget} />
        <BANTBar label="صلاحية القرار" value={lead.bant_authority} />
        <BANTBar label="الحاجة" value={lead.bant_need} />
        <BANTBar label="التوقيت" value={lead.bant_timeline} />
      </div>

      {/* AI notes (expandable) */}
      {lead.ai_notes && (
        <div>
          <button
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors"
          >
            <Bot size={12} className="text-gold-primary" />
            <span className="font-cairo">ملاحظات الذكاء الاصطناعي</span>
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
          {expanded && (
            <p className="mt-1.5 text-xs text-gray-400 bg-gray-800/50 rounded-lg p-2.5 leading-relaxed font-cairo">
              {lead.ai_notes}
            </p>
          )}
        </div>
      )}

      {/* Unverified warning — a lead the system couldn't confirm as real/reachable */}
      {lead.verified_real === false && (
        <div className="flex items-start gap-1.5 text-xs text-yellow-300 bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-2 font-cairo">
          <AlertTriangle size={13} className="shrink-0 mt-0.5" />
          <span>لم يتم التأكد من أن هذا العميل حقيقي أو قابل للتواصل — راجع البيانات قبل القبول.</span>
        </div>
      )}

      {/* AI-drafted greeting (copilot) — editable, sent verbatim on approve */}
      {hasDraft && (
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5 text-xs text-gold-primary font-cairo">
            <MessageSquare size={13} />
            <span>رسالة الترحيب المقترحة (عدّلها إن أردت)</span>
          </div>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={4}
            dir="auto"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo leading-relaxed resize-y"
          />
        </div>
      )}

      {/* Reject reason input */}
      {rejectMode && (
        <div className="flex flex-wrap gap-1.5">
          {REJECT_REASONS.map((r) => (
            <button key={r} onClick={() => handleReject(r)} disabled={loading !== null}
              className="text-xs px-2 py-1 rounded-full border border-gray-700 text-gray-300 hover:border-red-500/50 hover:text-red-300 font-cairo disabled:opacity-50">
              {r}
            </button>
          ))}
        </div>
      )}
      {rejectMode && (
        <input
          type="text"
          placeholder="أو اكتب سبباً آخر ثم Enter (اختياري)..."
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-red-500 font-cairo"
          autoFocus
          onKeyDown={(e) => {
            if (e.key === 'Escape') { setRejectMode(false); setRejectReason('') }
            if (e.key === 'Enter') handleReject()
          }}
        />
      )}

      {/* Action buttons */}
      <div className="flex gap-2 pt-1">
        <button
          onClick={handleApprove}
          disabled={loading !== null}
          className="flex-1 flex items-center justify-center gap-1.5 bg-green-500/10 hover:bg-green-500/20 text-green-400 border border-green-500/30 rounded-lg py-2 text-sm font-semibold transition-colors disabled:opacity-50 font-cairo"
        >
          {loading === 'approve' ? (
            <span className="w-4 h-4 border-2 border-green-400 border-t-transparent rounded-full animate-spin" />
          ) : (
            <CheckCircle size={15} />
          )}
          {hasDraft ? 'قبول وإرسال' : 'قبول للتواصل'}
        </button>

        <button
          onClick={() => handleReject()}
          disabled={loading !== null}
          className={clsx(
            'flex-1 flex items-center justify-center gap-1.5 border rounded-lg py-2 text-sm font-semibold transition-colors disabled:opacity-50 font-cairo',
            rejectMode
              ? 'bg-red-500/20 text-red-400 border-red-500/50'
              : 'bg-red-500/10 hover:bg-red-500/20 text-red-400 border-red-500/30'
          )}
        >
          {loading === 'reject' ? (
            <span className="w-4 h-4 border-2 border-red-400 border-t-transparent rounded-full animate-spin" />
          ) : (
            <XCircle size={15} />
          )}
          {rejectMode ? 'تأكيد الرفض' : 'رفض'}
        </button>

        <button
          onClick={handleManual}
          disabled={loading !== null}
          title="ينتقل العميل لمسار المبيعات وتتواصل معه بنفسك — بدون رسائل تلقائية"
          className="flex-1 flex items-center justify-center gap-1.5 bg-gray-500/10 hover:bg-gray-500/20 text-gray-400 border border-gray-500/30 rounded-lg py-2 text-sm font-semibold transition-colors disabled:opacity-50 font-cairo"
        >
          {loading === 'manual' ? (
            <span className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
          ) : (
            <UserCheck size={15} />
          )}
          سأتولاه
        </button>
      </div>

      {/* Cancel reject */}
      {rejectMode && (
        <button
          onClick={() => { setRejectMode(false); setRejectReason('') }}
          className="w-full text-xs text-gray-500 hover:text-gray-300 transition-colors py-1 font-cairo"
        >
          إلغاء
        </button>
      )}
    </div>
  )
}
