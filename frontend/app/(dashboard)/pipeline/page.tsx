'use client'

import { useState, useCallback, useRef, DragEvent } from 'react'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { useRouter } from 'next/navigation'
import { MessageSquare } from 'lucide-react'
import { leadsApi } from '@/lib/api'
import type { Lead, LeadStage } from '@/lib/types'
import { PIPELINE_STAGES } from '@/lib/stages'

interface Column {
  stage: LeadStage
  label: string
  color: string
  headerColor: string
  matchStages?: string[]  // when set, the column collects leads in any of these stages
}

const COLUMNS: Column[] = [
  // Incoming: leads from every source that haven't entered the sales flow yet
  // (scraped, AI-qualified, awaiting review). Drag them right to progress them.
  { stage: 'new', label: 'وارد', matchStages: ['new', 'pending_review', 'approved'], color: 'border-gray-500/30', headerColor: 'text-gray-300' },
  ...PIPELINE_STAGES.map((s) => ({
    stage: s.value,
    label: s.label,
    color: s.color,
    headerColor: s.headerColor,
  })),
]

function ScoreBadge({ score }: { score?: number }) {
  if (score === undefined) return null
  return (
    <span className={clsx(
      'text-xs font-bold px-1.5 py-0.5 rounded',
      score >= 70 ? 'text-green-400 bg-green-500/10'
      : score >= 50 ? 'text-yellow-400 bg-yellow-500/10'
      : 'text-red-400 bg-red-500/10'
    )}>
      {score}
    </span>
  )
}

function LeadCard({
  lead,
  onDragStart,
  onOpen,
}: {
  lead: Lead
  onDragStart: (e: DragEvent, leadId: string) => void
  onOpen: (leadId: string) => void
}) {
  // A drag ends with a click event in some browsers — suppress that so a drop doesn't
  // also navigate. Real clicks (no drag) still open the conversation.
  const draggedRef = useRef(false)
  return (
    <div
      draggable
      onDragStart={(e) => { draggedRef.current = true; onDragStart(e, lead.id) }}
      onDragEnd={() => { setTimeout(() => { draggedRef.current = false }, 0) }}
      onClick={() => { if (draggedRef.current) return; onOpen(lead.id) }}
      title="افتح المحادثة"
      className="group bg-gray-900 border border-gray-700 rounded-lg p-3 cursor-pointer hover:border-gold-primary/50 transition-colors select-none"
    >
      <div className="flex items-start justify-between gap-1 mb-1.5">
        <span className="text-sm font-medium text-white font-cairo leading-snug">
          {lead.company || lead.name || 'غير محدد'}
        </span>
        <ScoreBadge score={lead.bant_score} />
      </div>
      <div className="text-xs text-gray-500 font-cairo">
        {[lead.industry, lead.city].filter(Boolean).join(' · ') || '—'}
      </div>
      <div className="flex items-center justify-between mt-1">
        {lead.phone
          ? <span className="text-xs text-gray-600" dir="ltr">{lead.phone}</span>
          : <span />}
        <MessageSquare
          size={13}
          className="text-gray-600 group-hover:text-gold-primary transition-colors shrink-0"
        />
      </div>
    </div>
  )
}

function KanbanColumn({
  column,
  leads,
  onDrop,
  onDragOver,
  onDragLeave,
  isOver,
  onOpen,
}: {
  column: Column
  leads: Lead[]
  onDrop: (e: DragEvent, stage: LeadStage) => void
  onDragOver: (e: DragEvent) => void
  onDragLeave: () => void
  isOver: boolean
  onOpen: (leadId: string) => void
  onDragStart: (e: DragEvent, id: string) => void
} & { onDragStart: (e: DragEvent, id: string) => void }) {
  return (
    <div
      className={clsx(
        'flex flex-col min-w-[230px] max-w-[260px] bg-gray-900/50 border rounded-xl overflow-hidden transition-colors',
        column.color,
        isOver && 'ring-2 ring-gold-primary/50 bg-gold-primary/5'
      )}
      onDrop={(e) => onDrop(e, column.stage)}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
    >
      {/* Column header */}
      <div className={clsx('px-3 py-2.5 border-b border-gray-800 flex items-center justify-between')}>
        <span className={clsx('text-sm font-semibold font-cairo', column.headerColor)}>
          {column.label}
        </span>
        <span className="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded-full font-bold">
          {leads.length}
        </span>
      </div>

      {/* Cards */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2 min-h-[100px]">
        {leads.map((lead) => (
          <LeadCard
            key={lead.id}
            lead={lead}
            onOpen={onOpen}
            onDragStart={(e, id) => {
              e.dataTransfer.setData('leadId', id)
              e.dataTransfer.effectAllowed = 'move'
            }}
          />
        ))}
        {leads.length === 0 && (
          <div className="text-center text-gray-700 text-xs py-4 font-cairo">اسحب هنا</div>
        )}
      </div>
    </div>
  )
}

export default function PipelinePage() {
  const router = useRouter()
  const handleOpen = useCallback((leadId: string) => {
    // Open the lead's conversation (WhatsApp or email) in the inbox.
    router.push(`/inbox?lead=${leadId}`)
  }, [router])

  const { data, mutate, isLoading } = useSWR(
    'leads/pipeline',
    () => leadsApi.list({ per_page: 200 }).then((r) => r.data),
    { revalidateOnFocus: true }
  )
  // Backend returns { total, leads: [...] }. (Older shapes used items — keep a fallback.)
  const leads: Lead[] = data?.leads || data?.items || []

  const [dragOverStage, setDragOverStage] = useState<LeadStage | null>(null)

  const handleDragStart = useCallback((e: DragEvent, leadId: string) => {
    e.dataTransfer.setData('leadId', leadId)
    e.dataTransfer.effectAllowed = 'move'
  }, [])

  const handleDragOver = useCallback((e: DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const handleDrop = useCallback(async (e: DragEvent, targetStage: LeadStage) => {
    e.preventDefault()
    setDragOverStage(null)
    const leadId = e.dataTransfer.getData('leadId')
    if (!leadId) return

    const lead = leads.find((l) => l.id === leadId)
    if (!lead || lead.stage === targetStage) return

    // Optimistic update
    const updatedLeads = leads.map((l) =>
      l.id === leadId ? { ...l, stage: targetStage } : l
    )
    mutate({ ...data, leads: updatedLeads }, false)

    try {
      await leadsApi.updateStage(leadId, targetStage)
      toast.success(`نُقل العميل إلى "${COLUMNS.find((c) => c.stage === targetStage)?.label}"`)
    } catch {
      toast.error('فشل تحديث المرحلة')
      mutate()
    }
  }, [leads, data, mutate])

  const getColumnLeads = (col: Column) =>
    leads.filter((l) => col.matchStages ? col.matchStages.includes(l.stage) : l.stage === col.stage)

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white font-cairo">خط الأنابيب</h1>
          <p className="text-gray-400 text-sm mt-1">Sales Pipeline — {leads.length} lead</p>
        </div>
      </div>

      <div className="overflow-x-auto pb-4">
        <div className="flex gap-3 min-w-max">
          {COLUMNS.map((col) => (
            <KanbanColumn
              key={col.stage}
              column={col}
              leads={getColumnLeads(col)}
              onOpen={handleOpen}
              onDragStart={handleDragStart}
              onDrop={handleDrop}
              onDragOver={(e) => { handleDragOver(e); setDragOverStage(col.stage) }}
              onDragLeave={() => setDragOverStage(null)}
              isOver={dragOverStage === col.stage}
            />
          ))}
        </div>
      </div>

      <p className="text-xs text-gray-600 text-center font-cairo">
        اسحب البطاقات بين الأعمدة لتحديث المرحلة
      </p>
    </div>
  )
}
