'use client'

import { useState, useCallback, DragEvent } from 'react'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { leadsApi } from '@/lib/api'
import type { Lead, LeadStage } from '@/lib/types'
import { PIPELINE_STAGES } from '@/lib/stages'

interface Column {
  stage: LeadStage
  label: string
  color: string
  headerColor: string
}

const COLUMNS: Column[] = PIPELINE_STAGES.map((s) => ({
  stage: s.value,
  label: s.label,
  color: s.color,
  headerColor: s.headerColor,
}))

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
}: {
  lead: Lead
  onDragStart: (e: DragEvent, leadId: string) => void
}) {
  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, lead.id)}
      className="bg-gray-900 border border-gray-700 rounded-lg p-3 cursor-grab active:cursor-grabbing hover:border-gray-600 transition-colors select-none"
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
      {lead.phone && (
        <div className="text-xs text-gray-600 mt-1" dir="ltr">{lead.phone}</div>
      )}
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
}: {
  column: Column
  leads: Lead[]
  onDrop: (e: DragEvent, stage: LeadStage) => void
  onDragOver: (e: DragEvent) => void
  onDragLeave: () => void
  isOver: boolean
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
  const { data, mutate, isLoading } = useSWR(
    'leads/pipeline',
    () => leadsApi.list({ per_page: 200 }).then((r) => r.data),
    { revalidateOnFocus: true }
  )
  const leads: Lead[] = data?.items || []

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
    mutate({ ...data, items: updatedLeads }, false)

    try {
      await leadsApi.updateStage(leadId, targetStage)
      toast.success(`نُقل العميل إلى "${COLUMNS.find((c) => c.stage === targetStage)?.label}"`)
    } catch {
      toast.error('فشل تحديث المرحلة')
      mutate()
    }
  }, [leads, data, mutate])

  const getColumnLeads = (stage: LeadStage) =>
    leads.filter((l) => l.stage === stage)

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
              leads={getColumnLeads(col.stage)}
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
