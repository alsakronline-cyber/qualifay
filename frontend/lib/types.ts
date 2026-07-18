export type Plan = 'trial' | 'starter' | 'growth' | 'agency'

export type LeadStage =
  | 'new'
  | 'qualifying'
  | 'pending_review'
  | 'approved'
  | 'manual'
  | 'outreach'
  | 'replied'
  | 'meeting'
  | 'proposal'
  | 'negotiation'
  | 'won'
  | 'lost'
  | 'archived'

export type LeadStatus = 'active' | 'unsubscribed' | 'blocked' | 'invalid'

export type LeadSource =
  | 'google_maps'
  | 'websites'
  | 'directories'
  | 'tenders'
  | 'apollo'
  | 'linkedin'
  | 'facebook_groups'
  | 'enrichment'
  | 'competitor_ads'
  | 'manual'
  | 'pool'

export interface Tenant {
  id: string
  slug: string
  name: string
  plan: Plan
  language: string
  email?: string
  phone?: string
  created_at: string
}

export interface Lead {
  id: string
  tenant_id: string
  source: LeadSource
  name?: string
  phone?: string
  email?: string
  wa_reachable?: boolean | null
  reach?: 'whatsapp' | 'phone' | 'phone_no_wa' | 'email' | 'none'
  company?: string
  industry?: string
  company_size?: string
  city?: string
  country?: string
  website?: string
  bant_score?: number
  bant_budget?: number
  bant_authority?: number
  bant_need?: number
  bant_timeline?: number
  bant_reason?: string
  stage: LeadStage
  status: LeadStatus
  language: string
  ai_notes?: string
  assigned_to?: string
  created_at: string
  updated_at?: string
}

export interface WaInstance {
  id: string
  tenant_id: string
  instance_name: string
  display_name?: string
  status: 'connected' | 'disconnected' | 'connecting' | 'qr_needed'
  phone_number?: string
  day_of_life: number
  daily_wa_cap: number
  sent_today_wa: number
  warmup_complete: boolean
  paused?: boolean
  warmup_started_at?: string
  last_connected_at?: string
  created_at: string
}

export interface Conversation {
  id: string
  tenant_id: string
  instance_id: string
  instance_name?: string
  stage?: LeadStage
  channel?: 'whatsapp' | 'email'
  contact_phone: string
  contact_name?: string
  lead_id?: string
  unread_count: number
  ai_enabled: boolean
  last_message?: string
  last_message_at?: string
  created_at: string
}

export interface Message {
  id: string
  conversation_id?: string
  direction: 'inbound' | 'outbound'
  content: string
  media_url?: string
  media_type?: string
  message_type?: 'text' | 'image' | 'video' | 'audio' | 'document' | 'sticker' | 'email'
  has_media?: boolean
  attachments?: { filename: string; content_type?: string; size?: number }[]
  is_ai_generated: boolean
  wa_message_id?: string
  status?: 'pending' | 'sent' | 'delivered' | 'read' | 'failed'
  created_at: string
}

export interface Notification {
  id: string
  tenant_id: string
  type: string
  title: string
  message?: string
  body?: string
  read?: boolean
  read_at?: string | null
  data?: Record<string, unknown>
  created_at: string
}

export interface Campaign {
  id: string
  tenant_id: string
  name: string
  status: 'draft' | 'running' | 'paused' | 'completed' | 'failed'
  target_stage?: LeadStage
  template_id?: string
  sent_count: number
  replied_count: number
  created_at: string
}

export interface ScrapeJob {
  id: string
  tenant_id: string
  source: LeadSource
  status: 'pending' | 'running' | 'completed' | 'failed'
  config: Record<string, unknown>
  leads_found: number
  leads_saved: number
  error_message?: string
  started_at?: string
  completed_at?: string
  created_at: string
}

export interface DashboardStats {
  total_leads: number
  pending_review: number
  wa_messages_today: number
  active_campaigns: number
  recent_leads: Lead[]
  recent_messages: Message[]
  instances: WaInstance[]
}

export interface AuthUser {
  id: string
  email: string
  name: string
  tenant: Tenant
  role: 'owner' | 'admin' | 'agent'
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}
