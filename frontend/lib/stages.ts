import type { LeadStage } from './types'

// The canonical sales-pipeline stages, in board order (used by the Kanban board, the
// lead-detail stage picker, and the inbox per-conversation picker). Kept in ONE place so
// the board columns and the stages the AI/sync assign can never drift apart again — the
// mismatch between them is exactly what left the pipeline looking empty.
export interface PipelineStageDef {
  value: LeadStage
  label: string
  color: string        // border color for the Kanban column
  headerColor: string  // text color for the column header
}

export const PIPELINE_STAGES: PipelineStageDef[] = [
  { value: 'replied', label: 'استجاب', color: 'border-yellow-500/30', headerColor: 'text-yellow-400' },
  { value: 'qualifying', label: 'تأهيل', color: 'border-blue-500/30', headerColor: 'text-blue-400' },
  { value: 'meeting', label: 'اجتماع', color: 'border-cyan-500/30', headerColor: 'text-cyan-400' },
  { value: 'proposal', label: 'عرض سعر', color: 'border-purple-500/30', headerColor: 'text-purple-400' },
  { value: 'negotiation', label: 'تفاوض', color: 'border-orange-500/30', headerColor: 'text-orange-400' },
  { value: 'won', label: 'مربوح', color: 'border-green-500/30', headerColor: 'text-green-400' },
  { value: 'lost', label: 'خسارة', color: 'border-red-500/30', headerColor: 'text-red-400' },
]

// Labels for every stage (including non-pipeline ones like pending_review) for display.
export const STAGE_LABELS: Record<string, string> = {
  new: 'جديد', qualifying: 'تأهيل', pending_review: 'قيد المراجعة', approved: 'مقبول',
  manual: 'يدوي', outreach: 'تواصل', replied: 'استجاب', meeting: 'اجتماع',
  proposal: 'عرض سعر', negotiation: 'تفاوض', won: 'مربوح', lost: 'خسارة', archived: 'مؤرشف',
}
