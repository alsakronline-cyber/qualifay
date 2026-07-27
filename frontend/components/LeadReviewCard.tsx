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
}

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
  google_maps: 'bg-blue-500/10 text-blue-400',
  websites: 'bg-purple-500/10 text-purple-400',
  directories: 'bg-indigo-500/10 text-indigo-400',
  tenders: 'bg-orange-500/10 text-orange-400',
  apollo: 'bg-pink-500/10 text-pink-400',
  linkedin: 'bg-sky-500/10 text-sky-400',
  facebook_groups: 'bg-blue-600/10 text-blue-500',
  enrichment: 'bg-teal-500/10 text-teal-400',
  competitor_ads: 'bg-red-500/10 text-red-400',
  manual: 'bg-gray-500/10 text-gray-400',
  pool: 'bg-gold-primary/10 text-gold-primary',
}

function BANTBar({ label, value }: { label: string; value?: number }) {
  const pct = Math.min((value ?? 0) / 25, 1) * 100
  return (
    <div className="flex items-center gap-2">
      <span className="w-4 text-xs font-bold text-gray-400">{label}</span>
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

  async function handleReject() {
    if (!rejectMode) { setRejectMode(true); return }
    setLoading('reject')
    await onReject(lead.id, rejectReason || undefined)
    setLoading(null)
    setRejectMode(false)
    setRejectReason('')
  }

  async function handleManual() {
    setLoading('manual')
    await onTakeManually(lead.id)
    setLoading(null)
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3 hover:border-gray-700 transition-colors">
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
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

      {/* BANT mini bars */}
      <div className="space-y-1.5">
        <BANTBar label="B" value={lead.bant_budget} />
        <BANTBar label="A" value={lead.bant_authority} />
        <BANTBar label="N" value={lead.bant_need} />
        <BANTBar label="T" value={lead.bant_timeline} />
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

      {/* BANT reason */}
      {lead.bant_reason && (
        <p className="text-xs text-gray-500 italic line-clamp-2 font-cairo">{lead.bant_reason}</p>
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
        <input
          type="text"
          placeholder="سبب الرفض (اختياري)..."
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
          {hasDraft ? 'قبول وإرسال' : 'قبول'}
        </button>

        <button
          onClick={handleReject}
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
          className="flex-1 flex items-center justify-center gap-1.5 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded-lg py-2 text-sm font-semibold transition-colors disabled:opacity-50 font-cairo"
        >
          {loading === 'manual' ? (
            <span className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
          ) : (
            <UserCheck size={15} />
          )}
          يدوي
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
