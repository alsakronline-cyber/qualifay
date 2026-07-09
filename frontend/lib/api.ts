import axios, { AxiosError } from 'axios'

const API = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// Auth token interceptor
API.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('auth_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
  }
  return config
})

// 401 redirect interceptor
API.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      localStorage.removeItem('auth_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authApi = {
  login: (identifier: string, password: string) => {
    // `identifier` may be an email or a phone number — the backend tries both.
    const form = new URLSearchParams()
    form.append('username', identifier)
    form.append('password', password)
    return API.post('/v1/auth/login', form, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
  },
  register: (data: {
    tenant_name: string
    tenant_slug: string
    email: string
    phone?: string
    password: string
    full_name: string
    language?: string
  }) => API.post('/v1/auth/register-tenant', data),
  me: () => API.get('/v1/auth/me'),
  logout: () => API.post('/v1/auth/logout'),
  refresh: () => API.post('/v1/auth/refresh'),
}

// ── Leads ─────────────────────────────────────────────────────────────────────
export const leadsApi = {
  list: (params?: {
    stage?: string
    source?: string
    min_score?: number
    max_score?: number
    search?: string
    page?: number
    per_page?: number
  }) => API.get('/v1/leads', { params }),

  reviewQueue: () => API.get('/v1/leads/review-queue'),

  get: (id: string) => API.get(`/v1/leads/${id}`),

  getOne: (id: string) => API.get(`/v1/leads/${id}`),

  update: (id: string, data: Record<string, unknown>) => API.patch(`/v1/leads/${id}`, data),

  approve: (id: string) => API.post(`/v1/leads/${id}/approve`),

  reject: (id: string, reason?: string) =>
    API.post(`/v1/leads/${id}/reject`, { reason }),

  takeManually: (id: string) =>
    API.post(`/v1/leads/${id}/take-manually`),

  bulkApprove: (ids: string[], templateId?: string) =>
    API.post('/v1/leads/bulk-approve', { ids, template_id: templateId || null }),

  checkReachability: (ids?: string[]) =>
    API.post('/v1/leads/check-reachability', { ids: ids || null }),

  exportCsv: (params?: { stage?: string; source?: string; search?: string }) =>
    API.get('/v1/leads/export', { params, responseType: 'blob' }),
  importCsv: (file: File) => {
    const fd = new FormData(); fd.append('file', file)
    return API.post('/v1/leads/import', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
  },

  enrichLinkedIn: (ids?: string[]) =>
    API.post('/v1/leads/enrich-linkedin', { ids: ids || null }),

  poolSearch: (params: {
    industry?: string
    city?: string
    min_score?: number
    page?: number
  }) => API.get('/v1/leads/pool/search', { params }),

  poolClaim: (poolId: string) =>
    API.post(`/v1/leads/pool/${poolId}/claim`),

  updateStage: (id: string, stage: string) =>
    API.patch(`/v1/leads/${id}`, { stage }),
}

// ── Activity ──────────────────────────────────────────────────────────────────
export const activityApi = {
  list: (params: { entity_id?: string; entity_type?: string; limit?: number }) =>
    API.get('/v1/activity', { params }),
}

// ── Settings ──────────────────────────────────────────────────────────────────
export const settingsApi = {
  getProfile: () => API.get('/v1/settings/profile'),
  updateProfile: (data: Record<string, unknown>) => API.patch('/v1/settings/profile', data),
}

// ── WA Instances ──────────────────────────────────────────────────────────────
export const instancesApi = {
  list: () => API.get('/v1/instances'),
  create: (name: string) => API.post('/v1/instances', { instance_name: name }),
  delete: (id: string, purge = false) => API.delete(`/v1/instances/${id}`, { params: { purge } }),
  getQr: (id: string) => API.get(`/v1/instances/${id}/qr`),
  getStatus: (id: string) => API.get(`/v1/instances/${id}/status`),
  getWarmup: (id: string) => API.get(`/v1/instances/${id}/warmup`),
  reconnect: (id: string) => API.post(`/v1/instances/${id}/reconnect`),
  disconnect: (id: string) => API.post(`/v1/instances/${id}/disconnect`),
  sync: (id: string) => API.post(`/v1/instances/${id}/sync`),
  toggleAI: (id: string, enabled: boolean) =>
    API.patch(`/v1/instances/${id}/ai-toggle`, { ai_suggest_enabled: enabled }),

  pause: (id: string, paused: boolean) =>
    API.patch(`/v1/instances/${id}/pause`, { paused }),
}

// ── Conversations ─────────────────────────────────────────────────────────────
export const conversationsApi = {
  list: (params?: { page?: number; per_page?: number; instance_name?: string; channel?: string; search?: string; lead_id?: string }) =>
    API.get('/v1/conversations', { params }),

  get: (id: string) => API.get(`/v1/conversations/${id}`),

  sendMedia: (id: string, file: File, caption = '') => {
    const form = new FormData()
    form.append('file', file)
    form.append('caption', caption)
    return API.post(`/v1/conversations/${id}/media`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  deleteMessage: (conversationId: string, messageId: string) =>
    API.delete(`/v1/conversations/${conversationId}/messages/${messageId}`),

  sendVoice: (id: string, blob: Blob) => {
    const form = new FormData()
    form.append('file', blob, 'voice.webm')
    return API.post(`/v1/conversations/${id}/voice`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  messages: (id: string, params?: { page?: number; per_page?: number }) =>
    API.get(`/v1/conversations/${id}/messages`, { params }),

  getMediaBlob: (conversationId: string, messageId: string) =>
    API.get(`/v1/conversations/${conversationId}/messages/${messageId}/media`, { responseType: 'blob' }),

  sendMessage: (id: string, content: string) =>
    API.post(`/v1/conversations/${id}/messages`, { content }),

  toggleAi: (id: string, enabled: boolean) =>
    API.patch(`/v1/conversations/${id}`, { ai_enabled: enabled }),

  rename: (id: string, contactName: string) =>
    API.patch(`/v1/conversations/${id}`, { contact_name: contactName }),

  setStage: (id: string, stage: string) =>
    API.patch(`/v1/conversations/${id}/stage`, { stage }),

  ensureLead: (id: string) =>
    API.post(`/v1/conversations/${id}/lead`),

  markRead: (id: string) =>
    API.post(`/v1/conversations/${id}/mark-read`),

  suggestReply: (id: string) =>
    API.post(`/v1/conversations/${id}/suggest-reply`, {}),

  sendApproved: (id: string, message: string, waJid: string, instanceName: string) =>
    API.post(`/v1/conversations/${id}/send-approved`, { message, wa_jid: waJid, instance_name: instanceName }),
}

// ── AI ────────────────────────────────────────────────────────────────────────
export const aiApi = {
  suggestReplies: (conversationId: string) =>
    API.post('/v1/ai/suggest-replies', { conversation_id: conversationId }),
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
export const dashboardApi = {
  stats: () => API.get('/v1/dashboard/stats'),
  activity: () => API.get('/v1/dashboard/activity'),
  analytics: () => API.get('/v1/dashboard/analytics'),
}

// ── Scrape ────────────────────────────────────────────────────────────────────
export const scrapeApi = {
  start: (config: {
    source: string
    query?: string
    location?: string
    industry?: string
    max_results?: number
    [key: string]: unknown
  }) => API.post('/v1/scrape/start', config),

  list: (params?: { page?: number; per_page?: number }) =>
    API.get('/v1/scrape/jobs', { params }),

  get: (id: string) => API.get(`/v1/scrape/jobs/${id}`),

  cancel: (id: string) => API.post(`/v1/scrape/jobs/${id}/cancel`),

  // Daily automatic search schedules
  createSchedule: (body: {
    source: string
    query?: string
    location?: string
    industry?: string
    max_results?: number
    hour_cairo?: number
    monthly_cap?: number
  }) => API.post('/v1/scrape/schedule', body),

  listSchedules: () => API.get('/v1/scrape/schedules'),

  toggleSchedule: (id: string, enabled: boolean) =>
    API.patch(`/v1/scrape/schedule/${id}`, null, { params: { enabled } }),

  deleteSchedule: (id: string) => API.delete(`/v1/scrape/schedule/${id}`),
}

// ── WhatsApp → Pipeline sync ──────────────────────────────────────────────────
export const waSyncApi = {
  syncToPipeline: () => API.post('/v1/conversations/sync-to-pipeline', {}),
}

// ── Notifications ─────────────────────────────────────────────────────────────
export const notificationsApi = {
  list: (params?: { unread?: boolean }) =>
    API.get('/v1/notifications', { params }),
  markRead: (id: string) => API.post(`/v1/notifications/${id}/read`),
  markAllRead: () => API.post('/v1/notifications/mark-all-read'),
}

// ── Campaigns ─────────────────────────────────────────────────────────────────
export const campaignsApi = {
  list: () => API.get('/v1/campaigns'),
  get: (id: string) => API.get(`/v1/campaigns/${id}`),
  create: (data: Record<string, unknown>) => API.post('/v1/campaigns', data),
  pause: (id: string) => API.post(`/v1/campaigns/${id}/pause`),
  resume: (id: string) => API.post(`/v1/campaigns/${id}/resume`),
}

// ── Agent Automation (browser-extension LinkedIn/Facebook sourcing) ───────────
export const agentApi = {
  getSetup: () => API.get('/v1/agent/setup'),
  regenerateKey: () => API.post('/v1/agent/regenerate-key'),
  listTasks: () => API.get('/v1/agent/tasks'),
  createTask: (body: {
    platform: 'linkedin' | 'facebook'
    type: string
    query?: string
    location?: string
    group_id?: string
    page_id?: string
    max_results?: number
    recurring?: boolean
    interval_minutes?: number
  }) => API.post('/v1/agent/tasks', body),
  deleteTask: (id: string) => API.delete(`/v1/agent/tasks/${id}`),
}

// ── Email system ──────────────────────────────────────────────────────────────
export const emailApi = {
  status: () => API.get('/v1/email/status'),
  sendTest: (to?: string) => API.post('/v1/email/test', { to: to || null }),
  // Multiple sending identities
  listAccounts: () => API.get('/v1/email/accounts'),
  createAccount: (body: {
    from_email: string; from_name?: string;
    smtp_host: string; smtp_port: number; smtp_user?: string; smtp_password: string;
    imap_host?: string; imap_port?: number;
  }) => API.post('/v1/email/accounts', body),
  updateAccount: (id: string, body: Record<string, unknown>) => API.patch(`/v1/email/accounts/${id}`, body),
  deleteAccount: (id: string) => API.delete(`/v1/email/accounts/${id}`),
  testAccount: (id: string, to?: string) => API.post(`/v1/email/accounts/${id}/test`, { to: to || null }),
}

// ── Message Templates ─────────────────────────────────────────────────────────
export const templatesApi = {
  list: () => API.get('/v1/templates'),
  create: (body: { name: string; channel: string; category?: string; subject?: string; body: string }) =>
    API.post('/v1/templates', body),
  update: (id: string, body: { name: string; channel: string; category?: string; subject?: string; body: string }) =>
    API.patch(`/v1/templates/${id}`, body),
  remove: (id: string) => API.delete(`/v1/templates/${id}`),
}

// ── Sequences (cadences) ──────────────────────────────────────────────────────
export interface SeqStep { delay_hours: number; channel: string; template_id?: string | null; subject?: string | null; body?: string | null }
export const sequencesApi = {
  list: () => API.get('/v1/sequences'),
  create: (body: { name: string; active: boolean; steps: SeqStep[] }) => API.post('/v1/sequences', body),
  update: (id: string, body: { name: string; active: boolean; steps: SeqStep[] }) => API.patch(`/v1/sequences/${id}`, body),
  remove: (id: string) => API.delete(`/v1/sequences/${id}`),
  enroll: (id: string, leadIds: string[]) => API.post(`/v1/sequences/${id}/enroll`, { lead_ids: leadIds }),
}

// ── Conversion Flows (booking / order / quote / callback) ─────────────────────
export const flowsApi = {
  list: () => API.get('/v1/flows'),
  create: (body: { name: string; type: string; active?: boolean; config?: Record<string, unknown> }) => API.post('/v1/flows', body),
  submissions: () => API.get('/v1/flows/submissions'),
  submit: (body: { flow_id: string; conversation_id?: string; lead_id?: string; data: Record<string, unknown>; send_confirmation?: boolean }) =>
    API.post('/v1/flows/submit', body),
}

export default API
