'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { format } from 'date-fns'
import { useRouter } from 'next/navigation'
import { Send, Bot, BotOff, Sparkles, MessageSquare, X, CheckCheck, Download, FileText, Loader2, KanbanSquare, Paperclip, Trash2, Search, Mic, UserRound, Pencil, Check, Mail } from 'lucide-react'
import { conversationsApi, waSyncApi, instancesApi, templatesApi, leadsApi } from '@/lib/api'
import type { Conversation, Message, WaInstance } from '@/lib/types'
import { PIPELINE_STAGES } from '@/lib/stages'
import { renderTemplate } from '@/lib/templates'
import ActionModal from '@/components/action-modal'
import { CalendarCheck } from 'lucide-react'

function MediaBubble({ conversationId, message }: { conversationId: string; message: Message }) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [mimeType, setMimeType] = useState<string>('')
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    let objectUrl: string | null = null
    setLoading(true)
    setError(false)
    conversationsApi
      .getMediaBlob(conversationId, message.id)
      .then((res) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(res.data)
        setBlobUrl(objectUrl)
        setMimeType(res.data.type || '')
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [conversationId, message.id])

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-xs opacity-70 py-4 px-2">
        <Loader2 size={14} className="animate-spin" />
        جارِ التحميل...
      </div>
    )
  }

  if (error || !blobUrl) {
    return <p className="text-xs opacity-70">{message.content || 'تعذر تحميل الملف'}</p>
  }

  // Resolve the effective kind: trust explicit message_type, else infer from fetched MIME.
  const t = message.message_type
  const isImage = t === 'image' || t === 'sticker' || (t === 'media' && mimeType.startsWith('image/'))
  const isVideo = t === 'video' || (t === 'media' && mimeType.startsWith('video/'))
  const isAudio = t === 'audio' || (t === 'media' && mimeType.startsWith('audio/'))

  if (isImage) {
    return (
      <a href={blobUrl} target="_blank" rel="noopener noreferrer" className="block">
        <img src={blobUrl} alt={message.content || 'image'} className="rounded-lg max-w-full max-h-72 object-contain" />
        {message.content && message.content !== '[media]' && <p className="text-sm mt-1.5">{message.content}</p>}
      </a>
    )
  }

  if (isVideo) {
    return (
      <div>
        <video src={blobUrl} controls className="rounded-lg max-w-full max-h-72" />
        {message.content && message.content !== '[media]' && <p className="text-sm mt-1.5">{message.content}</p>}
      </div>
    )
  }

  if (isAudio) {
    return <audio src={blobUrl} controls className="max-w-full" />
  }

  // document / other files
  const fileName = message.content && message.content !== '[media]' ? message.content : 'ملف'
  return (
    <a
      href={blobUrl}
      download={fileName}
      className="flex items-center gap-2 bg-black/20 rounded-lg px-3 py-2 hover:bg-black/30 transition-colors"
    >
      <FileText size={20} className="shrink-0" />
      <span className="text-sm truncate flex-1">{fileName}</span>
      <Download size={16} className="shrink-0" />
    </a>
  )
}

function fmtSize(bytes?: number): string {
  if (!bytes || bytes <= 0) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function AttachmentChip({ messageId, idx, att }: {
  messageId: string
  idx: number
  att: { filename: string; content_type?: string; size?: number }
}) {
  const [loading, setLoading] = useState(false)

  const download = async () => {
    if (loading) return
    setLoading(true)
    try {
      const res = await conversationsApi.getAttachmentBlob(messageId, idx)
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = att.filename || 'attachment'
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 4000)
    } catch {
      toast.error('تعذر تحميل المرفق')
    } finally {
      setLoading(false)
    }
  }

  return (
    <button
      onClick={download}
      disabled={loading}
      className="flex items-center gap-2 bg-black/20 rounded-lg px-3 py-2 hover:bg-black/30 transition-colors text-start w-full max-w-xs"
    >
      {loading ? <Loader2 size={18} className="shrink-0 animate-spin" /> : <FileText size={18} className="shrink-0" />}
      <span className="text-sm truncate flex-1">{att.filename || 'مرفق'}</span>
      {att.size ? <span className="text-xs opacity-60 shrink-0">{fmtSize(att.size)}</span> : null}
      <Download size={15} className="shrink-0 opacity-80" />
    </button>
  )
}

function ComposeModal({ onClose, onSent }: {
  onClose: () => void
  onSent: (conversationId: string) => void
}) {
  const [channel, setChannel] = useState<'whatsapp' | 'email'>('whatsapp')
  const [to, setTo] = useState('')
  const [subject, setSubject] = useState('')
  const [content, setContent] = useState('')
  const [sending, setSending] = useState(false)

  const send = async () => {
    if (!to.trim() || !content.trim() || sending) return
    setSending(true)
    try {
      const res = await conversationsApi.compose({
        channel, to: to.trim(),
        subject: channel === 'email' ? subject.trim() : undefined,
        content: content.trim(),
      })
      toast.success('تم الإرسال')
      onSent(res.data?.conversation_id)
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(msg || 'فشل الإرسال')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="w-full max-w-md bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-800">
          <h3 className="font-semibold text-white font-cairo">رسالة جديدة</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-white"><X size={18} /></button>
        </div>
        <div className="p-5 space-y-3">
          {/* Channel toggle */}
          <div className="flex gap-1 bg-gray-800 border border-gray-700 rounded-lg p-0.5">
            {([
              { key: 'whatsapp', label: 'واتساب', icon: MessageSquare },
              { key: 'email', label: 'بريد إلكتروني', icon: Mail },
            ] as const).map((c) => {
              const Icon = c.icon
              return (
                <button
                  key={c.key}
                  onClick={() => setChannel(c.key)}
                  className={clsx(
                    'flex-1 flex items-center justify-center gap-1.5 text-xs py-2 rounded-md font-cairo transition-colors',
                    channel === c.key ? 'bg-gold-primary text-gray-950 font-semibold' : 'text-gray-400 hover:text-white'
                  )}
                >
                  <Icon size={14} />{c.label}
                </button>
              )
            })}
          </div>
          <div>
            <label className="text-xs text-gray-400 font-cairo">{channel === 'email' ? 'البريد الإلكتروني' : 'رقم الهاتف'}</label>
            <input
              value={to}
              onChange={(e) => setTo(e.target.value)}
              dir="ltr"
              placeholder={channel === 'email' ? 'name@example.com' : '+201XXXXXXXXX'}
              className="w-full mt-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-gold-primary"
            />
          </div>
          {channel === 'email' && (
            <div>
              <label className="text-xs text-gray-400 font-cairo">الموضوع</label>
              <input
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="موضوع الرسالة"
                className="w-full mt-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo"
              />
            </div>
          )}
          <div>
            <label className="text-xs text-gray-400 font-cairo">الرسالة</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={4}
              placeholder="اكتب رسالتك..."
              className="w-full mt-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo resize-none"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 px-5 py-3.5 border-t border-gray-800">
          <button onClick={onClose} className="text-sm text-gray-400 hover:text-white px-3 py-2 font-cairo">إلغاء</button>
          <button
            onClick={send}
            disabled={sending || !to.trim() || !content.trim()}
            className="flex items-center gap-1.5 text-sm bg-gold-primary text-gray-950 font-semibold rounded-lg px-4 py-2 disabled:opacity-50 hover:brightness-110 transition font-cairo"
          >
            {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            إرسال
          </button>
        </div>
      </div>
    </div>
  )
}

export default function InboxPage() {
  const router = useRouter()
  const [openingLead, setOpeningLead] = useState(false)
  const [editingName, setEditingName] = useState(false)
  const [nameInput, setNameInput] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [msgInput, setMsgInput] = useState('')
  const [sending, setSending] = useState(false)
  // P4: AI suggestion state
  const [aiSuggestion, setAiSuggestion] = useState<string>('')
  const [editedSuggestion, setEditedSuggestion] = useState<string>('')
  const [loadingSuggestion, setLoadingSuggestion] = useState(false)
  const [sendingApproved, setSendingApproved] = useState(false)
  const [syncingPipeline, setSyncingPipeline] = useState(false)
  const [composeOpen, setComposeOpen] = useState(false)
  // Which WhatsApp instance to show. '' = all instances (default).
  const [instanceFilter, setInstanceFilter] = useState<string>('')
  // Channel filter: '' = all, 'whatsapp', or 'email'.
  const [channelFilter, setChannelFilter] = useState<string>('')
  const [search, setSearch] = useState('')
  const [uploadingMedia, setUploadingMedia] = useState(false)
  const [recording, setRecording] = useState(false)
  const [recordSecs, setRecordSecs] = useState(0)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const recordTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const cancelRecordRef = useRef(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const handleSyncToPipeline = useCallback(async () => {
    setSyncingPipeline(true)
    try {
      await waSyncApi.syncToPipeline()
      toast.success('بدأت مزامنة المحادثات — ستظهر النتائج في خط الأنابيب خلال دقائق')
    } catch {
      toast.error('فشلت المزامنة')
    } finally {
      setSyncingPipeline(false)
    }
  }, [])

  // Connected WhatsApp instances — used for the filter dropdown and to label chats.
  const { data: instData } = useSWR('wa-instances', () => instancesApi.list().then((r) => r.data))
  const instances: WaInstance[] = Array.isArray(instData) ? instData : (instData?.items || instData?.instances || [])

  // Templates for the quick-insert picker in the reply box.
  const { data: tplData } = useSWR('templates', () => templatesApi.list().then((r) => r.data))
  const templates: { id: string; name: string; channel: string; body: string }[] = Array.isArray(tplData) ? tplData : []
  const [showTemplates, setShowTemplates] = useState(false)
  const [showAction, setShowAction] = useState(false)

  // Conversations list. The instance filter is part of the SWR key so switching it
  // refetches; an empty filter lists chats from every instance (the backend returns
  // all of them unless instance_name is passed).
  const { data: convData, mutate: mutateConvs } = useSWR(
    ['conversations', instanceFilter, channelFilter, search],
    () => conversationsApi.list({
      limit: 200,   // server default is 50 — show the full inbox, not just the newest 50
      ...(instanceFilter ? { instance_name: instanceFilter } : {}),
      ...(channelFilter ? { channel: channelFilter } : {}),
      ...(search.trim() ? { search: search.trim() } : {}),
    }).then((r) => r.data),
    { refreshInterval: 4000 }
  )
  const conversations: Conversation[] = Array.isArray(convData) ? convData : (convData?.items || convData?.conversations || [])

  // Messages for selected conversation — poll faster so incoming replies show quickly.
  const { data: msgData, mutate: mutateMsgs } = useSWR(
    selectedId ? `conversations/${selectedId}/messages` : null,
    () => conversationsApi.messages(selectedId!).then((r) => r.data),
    { refreshInterval: 2000 }
  )
  const messages: Message[] = Array.isArray(msgData) ? msgData : (msgData?.items || msgData?.messages || [])

  // Fallback fetch: a deep-linked conversation (from a lead profile) may not be in the
  // recent list, so fetch it directly by id when it isn't already loaded.
  const { data: selectedConvData } = useSWR(
    selectedId ? `conversation/${selectedId}` : null,
    () => conversationsApi.get(selectedId!).then((r) => r.data)
  )
  const selectedConv = conversations.find((c) => c.id === selectedId) || selectedConvData

  // The selected chat's lead — so templates can fill {{company}}/{{industry}}/{{city}}.
  const { data: selectedLead } = useSWR(
    selectedConv?.lead_id ? `lead/${selectedConv.lead_id}` : null,
    () => leadsApi.getOne(selectedConv!.lead_id!).then((r) => r.data)
  )

  // Deep link from the lead profile: /inbox?lead=<id> or /inbox?conversation=<id>.
  // Read from window (client-only effect) to avoid the useSearchParams Suspense rule.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const convParam = params.get('conversation')
    if (convParam) { setSelectedId(convParam); return }
    const leadParam = params.get('lead')
    if (!leadParam) return
    conversationsApi.list({ lead_id: leadParam }).then((r) => {
      const list = Array.isArray(r.data) ? r.data : (r.data?.items || r.data?.conversations || [])
      if (list.length) setSelectedId(list[0].id)
      else toast('لا توجد محادثة واتساب لهذا العميل')
    }).catch(() => {})
  }, [])

  // A notification clicked while already on the inbox: open that thread without a reload.
  useEffect(() => {
    const onSelect = (e: Event) => {
      const id = (e as CustomEvent).detail
      if (typeof id === 'string' && id) setSelectedId(id)
    }
    window.addEventListener('qualifay:selectConversation', onSelect)
    return () => window.removeEventListener('qualifay:selectConversation', onSelect)
  }, [])

  const selectedIsEmail = selectedConv?.channel === 'email'
  // A WhatsApp conversation whose instance is no longer in the live list = a removed
  // number. Email conversations aren't tied to an instance, so never "disconnected".
  const selectedDisconnected = !selectedIsEmail
    && !!selectedConv?.instance_name
    && !instances.some((i) => i.instance_name === selectedConv.instance_name)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Clear suggestion when conversation changes
  useEffect(() => {
    setAiSuggestion('')
    setEditedSuggestion('')
    setEditingName(false)
  }, [selectedId])

  const handleSend = useCallback(async () => {
    if (!selectedId || !msgInput.trim()) return
    const content = msgInput.trim()
    setMsgInput('')          // clear immediately so the input feels instant
    setSending(true)
    // Optimistically show the message right away instead of waiting for the next poll.
    const optimistic = { id: 'temp-' + Date.now(), direction: 'outbound', content,
      message_type: 'text', created_at: new Date().toISOString(), is_ai_generated: false }
    mutateMsgs((cur: unknown) => {
      if (Array.isArray(cur)) return [...cur, optimistic]
      const o = cur as { items?: unknown[]; messages?: unknown[] } | undefined
      if (o?.items) return { ...o, items: [...o.items, optimistic] }
      if (o?.messages) return { ...o, messages: [...o.messages, optimistic] }
      return [optimistic]
    }, false)
    try {
      await conversationsApi.sendMessage(selectedId, content)
      mutateMsgs()
      mutateConvs()
    } catch {
      toast.error('فشل إرسال الرسالة')
      setMsgInput(content)   // restore on failure
      mutateMsgs()           // drop the optimistic bubble
    } finally {
      setSending(false)
    }
  }, [selectedId, msgInput, mutateMsgs, mutateConvs])

  const handleToggleAi = useCallback(async () => {
    if (!selectedId || !selectedConv) return
    try {
      await conversationsApi.toggleAi(selectedId, !selectedConv.ai_enabled)
      mutateConvs()
      toast.success(selectedConv.ai_enabled ? 'تم إيقاف الرد التلقائي' : 'تم تفعيل الرد التلقائي')
    } catch {
      toast.error('فشل تغيير الإعداد')
    }
  }, [selectedId, selectedConv, mutateConvs])

  // Manually set the pipeline phase for this chat (creates a lead if none exists yet).
  const handleSetStage = useCallback(async (stage: string) => {
    if (!selectedId) return
    try {
      await conversationsApi.setStage(selectedId, stage)
      mutateConvs()
      toast.success('تم تحديث المرحلة — يظهر في خط الأنابيب')
    } catch {
      toast.error('فشل تحديث المرحلة')
    }
  }, [selectedId, mutateConvs])

  // Open the lead profile for this chat — create the lead first if it doesn't exist yet.
  const handleOpenLead = useCallback(async () => {
    if (!selectedId || !selectedConv) return
    if (selectedConv.lead_id) {
      router.push(`/leads/${selectedConv.lead_id}`)
      return
    }
    setOpeningLead(true)
    try {
      const res = await conversationsApi.ensureLead(selectedId)
      const leadId = res.data?.lead_id
      if (leadId) router.push(`/leads/${leadId}`)
    } catch {
      toast.error('تعذر فتح ملف العميل')
    } finally {
      setOpeningLead(false)
    }
  }, [selectedId, selectedConv, router])

  const insertTemplate = useCallback((body: string) => {
    // Fill every {{var}} from the chat's lead (falls back to the contact name).
    setMsgInput(renderTemplate(body, {
      name: selectedLead?.name || selectedConv?.contact_name || '',
      company: selectedLead?.company || '',
      industry: selectedLead?.industry || '',
      city: selectedLead?.city || '',
    }))
    setShowTemplates(false)
  }, [selectedConv, selectedLead])

  const startRename = useCallback(() => {
    setNameInput(selectedConv?.contact_name || '')
    setEditingName(true)
  }, [selectedConv])

  const handleRename = useCallback(async () => {
    if (!selectedId) return
    try {
      await conversationsApi.rename(selectedId, nameInput.trim())
      setEditingName(false)
      mutateConvs()
    } catch {
      toast.error('فشل حفظ الاسم')
    }
  }, [selectedId, nameInput, mutateConvs])

  const handleAttachFile = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = '' // allow re-selecting the same file
    if (!file || !selectedId) return
    setUploadingMedia(true)
    try {
      await conversationsApi.sendMedia(selectedId, file, msgInput.trim())
      setMsgInput('')
      mutateMsgs()
      mutateConvs()
    } catch {
      toast.error('فشل إرسال الملف')
    } finally {
      setUploadingMedia(false)
    }
  }, [selectedId, msgInput, mutateMsgs, mutateConvs])

  const handleDeleteMessage = useCallback(async (messageId: string) => {
    if (!selectedId) return
    if (!confirm('حذف هذه الرسالة؟ سيتم حذفها من واتساب للطرفين إن أمكن.')) return
    try {
      await conversationsApi.deleteMessage(selectedId, messageId)
      mutateMsgs()
      mutateConvs()
    } catch {
      toast.error('فشل حذف الرسالة')
    }
  }, [selectedId, mutateMsgs, mutateConvs])

  const startRecording = useCallback(async () => {
    if (!selectedId) return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mr = new MediaRecorder(stream)
      chunksRef.current = []
      cancelRecordRef.current = false
      mr.ondataavailable = (e) => { if (e.data.size) chunksRef.current.push(e.data) }
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        if (recordTimerRef.current) clearInterval(recordTimerRef.current)
        setRecording(false)
        setRecordSecs(0)
        if (cancelRecordRef.current) return
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        if (blob.size < 800) return // ignore accidental blips
        setUploadingMedia(true)
        try {
          await conversationsApi.sendVoice(selectedId, blob)
          mutateMsgs()
          mutateConvs()
        } catch {
          toast.error('فشل إرسال الرسالة الصوتية')
        } finally {
          setUploadingMedia(false)
        }
      }
      mr.start()
      mediaRecorderRef.current = mr
      setRecording(true)
      setRecordSecs(0)
      recordTimerRef.current = setInterval(() => setRecordSecs((s) => s + 1), 1000)
    } catch {
      toast.error('تعذر الوصول إلى الميكروفون')
    }
  }, [selectedId, mutateMsgs, mutateConvs])

  const stopRecording = useCallback((cancel: boolean) => {
    cancelRecordRef.current = cancel
    mediaRecorderRef.current?.stop()
  }, [])

  // P4: Suggest reply via dedicated endpoint
  const handleSuggestReply = useCallback(async () => {
    if (!selectedId) return
    setLoadingSuggestion(true)
    setAiSuggestion('')
    setEditedSuggestion('')
    try {
      const res = await conversationsApi.suggestReply(selectedId)
      const suggestion = res.data?.suggestion || res.data?.suggestions?.[0] || ''
      setAiSuggestion(suggestion)
      setEditedSuggestion(suggestion)
    } catch {
      toast.error('فشل الحصول على اقتراح')
    } finally {
      setLoadingSuggestion(false)
    }
  }, [selectedId])

  // P4: Send the approved (possibly edited) suggestion
  const handleSendApproved = useCallback(async () => {
    if (!selectedId || !editedSuggestion.trim() || !selectedConv) return
    setSendingApproved(true)
    try {
      await conversationsApi.sendMessage(selectedId, editedSuggestion.trim())
      toast.success('تم إرسال الرسالة')
      setAiSuggestion('')
      setEditedSuggestion('')
      mutateMsgs()
      mutateConvs()
    } catch {
      toast.error('فشل إرسال الرسالة')
    } finally {
      setSendingApproved(false)
    }
  }, [selectedId, editedSuggestion, selectedConv, mutateMsgs, mutateConvs])

  return (
    <div className="flex h-[calc(100vh-6rem)] overflow-hidden rounded-xl border border-gray-800 bg-gray-900">
      {/* Conversation list */}
      <div className="w-72 shrink-0 border-l border-gray-800 flex flex-col overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800">
          <div className="flex items-center justify-between gap-2">
            <div>
              <h2 className="font-semibold text-white font-cairo text-sm">صندوق الوارد</h2>
              <p className="text-xs text-gray-500">{conversations.length} محادثة</p>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setComposeOpen(true)}
                title="بدء محادثة جديدة عبر واتساب أو البريد"
                className="flex items-center gap-1 text-[11px] bg-gold-primary text-gray-950 hover:brightness-110 rounded-lg px-2 py-1.5 font-cairo font-semibold transition"
              >
                <Send size={12} />
                رسالة جديدة
              </button>
              <button
                onClick={handleSyncToPipeline}
                disabled={syncingPipeline}
                title="تحليل المحادثات وتحويل المهتمين إلى عملاء في خط الأنابيب"
                className="flex items-center gap-1 text-[11px] bg-gold-primary/10 text-gold-primary border border-gold-primary/30 hover:bg-gold-primary/20 disabled:opacity-50 rounded-lg px-2 py-1.5 font-cairo transition-colors"
              >
                {syncingPipeline ? <Loader2 size={12} className="animate-spin" /> : <KanbanSquare size={12} />}
                مزامنة
              </button>
            </div>
          </div>
          {/* Channel filter — الكل / واتساب / بريد */}
          <div className="mt-2 flex gap-1 bg-gray-800 border border-gray-700 rounded-lg p-0.5">
            {([
              { key: '', label: 'الكل' },
              { key: 'whatsapp', label: 'واتساب' },
              { key: 'email', label: 'بريد' },
            ] as { key: string; label: string }[]).map((c) => (
              <button
                key={c.key}
                onClick={() => setChannelFilter(c.key)}
                className={clsx(
                  'flex-1 text-[11px] py-1 rounded-md font-cairo transition-colors',
                  channelFilter === c.key ? 'bg-gold-primary text-gray-950 font-semibold' : 'text-gray-400 hover:text-white'
                )}
              >
                {c.label}
              </button>
            ))}
          </div>
          {/* Search by number or contact name. */}
          <div className="relative mt-2">
            <Search size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="ابحث برقم أو اسم..."
              className="w-full bg-gray-800 border border-gray-700 rounded-lg pr-8 pl-2 py-1.5 text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo"
            />
            {search && (
              <button onClick={() => setSearch('')} className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300">
                <X size={13} />
              </button>
            )}
          </div>
          {/* Per-instance filter — only useful once more than one WhatsApp is connected. */}
          {instances.length > 1 && (
            <select
              value={instanceFilter}
              onChange={(e) => setInstanceFilter(e.target.value)}
              dir="rtl"
              className="mt-2 w-full bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo"
            >
              <option value="">كل الأرقام ({instances.length})</option>
              {instances.map((inst) => (
                <option key={inst.id} value={inst.instance_name}>
                  {inst.display_name || inst.phone_number || inst.instance_name}
                </option>
              ))}
            </select>
          )}
        </div>
        <div className="flex-1 overflow-y-auto divide-y divide-gray-800">
          {conversations.length === 0 && (
            <div className="text-center py-10 text-gray-600 font-cairo text-sm">لا توجد محادثات</div>
          )}
          {conversations.map((conv) => (
            <button
              key={conv.id}
              onClick={() => setSelectedId(conv.id)}
              className={clsx(
                'w-full text-right px-4 py-3 hover:bg-gray-800 transition-colors flex items-start gap-3',
                selectedId === conv.id && 'bg-gray-800'
              )}
            >
              {/* Avatar */}
              <div className="w-9 h-9 rounded-full bg-gradient-to-br from-gold-primary/30 to-gold-dark/30 flex items-center justify-center text-sm font-bold text-gold-primary shrink-0">
                {conv.contact_name?.charAt(0) || 'W'}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-1">
                  <span className="text-sm font-medium text-white truncate font-cairo">
                    {conv.contact_name || conv.contact_phone}
                  </span>
                  {conv.last_message_at && (
                    <span className="text-xs text-gray-600 shrink-0">
                      {format(new Date(conv.last_message_at), 'HH:mm')}
                    </span>
                  )}
                </div>
                {conv.contact_phone && (
                  <p className="text-xs text-gray-600 truncate" dir="ltr">{conv.contact_phone}</p>
                )}
                {conv.channel === 'email' ? (
                  <span className="inline-block mt-0.5 text-[10px] bg-gray-500/15 text-gray-400 border border-gray-500/25 rounded px-1.5 py-px font-cairo">
                    ✉ بريد إلكتروني
                  </span>
                ) : conv.instance_name && (() => {
                  const live = instances.find((i) => i.instance_name === conv.instance_name)
                  // Number was removed — history kept, but flag it so no one expects replies.
                  if (!live) return (
                    <span className="inline-block mt-0.5 text-[10px] bg-gray-700 text-gray-400 border border-gray-600 rounded px-1.5 py-px font-cairo">
                      رقم غير متصل
                    </span>
                  )
                  // Live number — only worth showing when more than one is connected.
                  if (instances.length > 1) return (
                    <span className="inline-block mt-0.5 text-[10px] bg-wa-green/15 text-wa-green border border-wa-green/25 rounded px-1.5 py-px font-cairo truncate max-w-full">
                      {live.display_name || conv.instance_name}
                    </span>
                  )
                  return null
                })()}
                <div className="flex items-center gap-1 mt-0.5">
                  <p className="text-xs text-gray-500 truncate flex-1">{conv.last_message || '—'}</p>
                  <div className="flex items-center gap-1 shrink-0">
                    {conv.ai_enabled && <Bot size={10} className="text-gold-primary" />}
                    {conv.unread_count > 0 && (
                      <span className="text-xs bg-wa-green text-white px-1.5 rounded-full font-bold">
                        {conv.unread_count}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Message thread */}
      {selectedConv ? (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Thread header */}
          <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
            <div>
              {editingName ? (
                <div className="flex items-center gap-1.5">
                  <input
                    autoFocus
                    value={nameInput}
                    onChange={(e) => setNameInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleRename(); if (e.key === 'Escape') setEditingName(false) }}
                    placeholder="اسم جهة الاتصال"
                    className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo w-44"
                  />
                  <button onClick={handleRename} title="حفظ" className="text-green-400 hover:text-green-300"><Check size={15} /></button>
                  <button onClick={() => setEditingName(false)} title="إلغاء" className="text-gray-500 hover:text-gray-300"><X size={15} /></button>
                </div>
              ) : (
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={handleOpenLead}
                    disabled={openingLead}
                    title="فتح ملف العميل"
                    className="group flex items-center gap-1.5 font-semibold text-white font-cairo hover:text-gold-primary transition-colors"
                  >
                    {selectedConv.contact_name || selectedConv.contact_phone}
                    {openingLead ? (
                      <Loader2 size={13} className="animate-spin text-gold-primary" />
                    ) : (
                      <UserRound size={13} className="text-gray-500 group-hover:text-gold-primary transition-colors" />
                    )}
                  </button>
                  <button onClick={startRename} title="تعديل الاسم" className="text-gray-500 hover:text-gold-primary transition-colors">
                    <Pencil size={12} />
                  </button>
                </div>
              )}
              <div className="flex items-center gap-2">
                <p className="text-xs text-gray-500">{selectedConv.contact_phone}</p>
                {selectedIsEmail ? (
                  <span className="text-[10px] bg-gray-500/15 text-gray-400 border border-gray-500/25 rounded px-1.5 py-px font-cairo">
                    ✉ بريد إلكتروني
                  </span>
                ) : selectedConv.instance_name && (
                  selectedDisconnected ? (
                    <span className="text-[10px] bg-gray-700 text-gray-400 border border-gray-600 rounded px-1.5 py-px font-cairo">
                      رقم غير متصل
                    </span>
                  ) : (
                    <span className="text-[10px] bg-wa-green/15 text-wa-green border border-wa-green/25 rounded px-1.5 py-px font-cairo">
                      {instances.find((i) => i.instance_name === selectedConv.instance_name)?.display_name || selectedConv.instance_name}
                    </span>
                  )
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              {/* Conversion action: book / order / quote / callback for this chat. */}
              <button
                onClick={() => setShowAction(true)}
                title="إجراء تحويل (حجز/طلب/عرض)"
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-gold-primary/30 bg-gold-primary/10 text-gold-primary hover:bg-gold-primary/20 transition-colors font-cairo"
              >
                <CalendarCheck size={13} /> إجراء
              </button>
              {/* Pipeline phase for this chat — empty until the user (or AI sync) sets one. */}
              <select
                value={PIPELINE_STAGES.some((s) => s.value === selectedConv.stage) ? selectedConv.stage : ''}
                onChange={(e) => handleSetStage(e.target.value)}
                className="text-xs px-3 py-1.5 rounded-lg border border-gray-700 bg-gray-800 text-gray-200 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo cursor-pointer"
              >
                <option value="" disabled>المرحلة…</option>
                {PIPELINE_STAGES.map((s) => (
                  <option key={s.value} value={s.value} className="bg-gray-900">{s.label}</option>
                ))}
              </select>
              <button
                onClick={handleToggleAi}
                className={clsx(
                  'flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-colors font-cairo',
                  selectedConv.ai_enabled
                    ? 'bg-green-500/10 text-green-400 border-green-500/30 hover:bg-green-500/20'
                    : 'bg-gray-800 text-gray-400 border-gray-700 hover:border-gray-600'
                )}
              >
                {selectedConv.ai_enabled ? <Bot size={12} /> : <BotOff size={12} />}
                {selectedConv.ai_enabled ? 'ذكاء اصطناعي: تفعيل' : 'ذكاء اصطناعي: إيقاف'}
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={clsx(
                  'flex items-center gap-1.5 group',
                  msg.direction === 'outbound' ? 'justify-end' : 'justify-start'
                )}
              >
                {/* Delete (revokes on WhatsApp + removes from inbox) — appears on hover. */}
                <button
                  onClick={() => handleDeleteMessage(msg.id)}
                  title="حذف الرسالة"
                  className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 transition-opacity shrink-0"
                >
                  <Trash2 size={13} />
                </button>
                <div
                  className={clsx(
                    'max-w-[70%] rounded-2xl px-4 py-2.5 text-sm relative shadow-sm',
                    msg.direction === 'outbound'
                      ? 'bubble-out rounded-tr-sm'
                      : 'bubble-in rounded-tl-sm'
                  )}
                >
                  {msg.has_media && selectedId ? (
                    <MediaBubble conversationId={selectedId} message={msg} />
                  ) : (
                    <span className="whitespace-pre-wrap break-words">{msg.content}</span>
                  )}
                  {Array.isArray(msg.attachments) && msg.attachments.length > 0 && (
                    <div className="mt-2 flex flex-col gap-1.5">
                      {msg.attachments.map((a, i) => (
                        <AttachmentChip key={i} messageId={msg.id} idx={i} att={a} />
                      ))}
                    </div>
                  )}
                  <div className={clsx(
                    'flex items-center gap-1 mt-1',
                    msg.direction === 'outbound' ? 'justify-end' : 'justify-start'
                  )}>
                    <span className="text-xs opacity-60">
                      {format(new Date(msg.created_at), 'HH:mm')}
                    </span>
                    {msg.is_ai_generated && (
                      <span className="text-xs bg-gold-primary/20 text-gold-primary px-1 rounded font-semibold">
                        AI
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          {/* P4: AI Suggestion Panel */}
          <div className="border-t border-gray-800">
            {/* AI Suggest button row — shown when no suggestion is active */}
            {!aiSuggestion && !loadingSuggestion && (
              <div className="px-4 py-2 flex items-center gap-2">
                <button
                  onClick={handleSuggestReply}
                  className="flex items-center gap-1.5 text-xs bg-gray-500/10 hover:bg-gray-500/20 text-gray-400 border border-gray-500/30 px-3 py-1.5 rounded-lg transition-colors font-cairo"
                >
                  <Sparkles size={12} />
                  اقتراح ذكاء اصطناعي ✨
                </button>
              </div>
            )}

            {/* Loading skeleton */}
            {loadingSuggestion && (
              <div className="px-4 py-3">
                <div className="flex items-center gap-1.5 text-xs text-gray-400 font-cairo mb-2">
                  <span className="w-3 h-3 border border-gray-400 border-t-transparent rounded-full animate-spin" />
                  جاري التفكير...
                </div>
                <div className="bg-gray-800/60 border border-gray-500/20 rounded-xl p-3 animate-pulse space-y-2">
                  <div className="h-3 bg-gray-700 rounded w-2/3" />
                  <div className="h-3 bg-gray-700 rounded w-full" />
                  <div className="h-3 bg-gray-700 rounded w-1/2" />
                </div>
              </div>
            )}

            {/* Suggestion box — editable */}
            {aiSuggestion && !loadingSuggestion && (
              <div className="px-4 pb-3 pt-2">
                <div className="bg-gray-800/60 border border-gray-500/30 rounded-xl p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="flex items-center gap-1.5 text-xs text-gray-400 font-cairo font-semibold">
                      <Sparkles size={11} />
                      اقتراح الذكاء الاصطناعي
                      <span className="text-gray-500 font-normal">AI Suggestion</span>
                    </span>
                    <button
                      onClick={() => { setAiSuggestion(''); setEditedSuggestion('') }}
                      className="text-gray-500 hover:text-gray-300 transition-colors"
                      title="تجاهل"
                    >
                      <X size={13} />
                    </button>
                  </div>
                  <textarea
                    value={editedSuggestion}
                    onChange={(e) => setEditedSuggestion(e.target.value)}
                    rows={3}
                    dir="rtl"
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500 font-cairo resize-none"
                  />
                  <div className="flex items-center gap-2 mt-2">
                    <button
                      onClick={() => { setAiSuggestion(''); setEditedSuggestion('') }}
                      className="text-xs text-gray-400 hover:text-white border border-gray-700 hover:border-gray-600 px-3 py-1.5 rounded-lg transition-colors font-cairo"
                    >
                      تجاهل
                    </button>
                    <button
                      onClick={handleSendApproved}
                      disabled={sendingApproved || !editedSuggestion.trim()}
                      className="flex items-center gap-1.5 text-xs bg-green-500/10 hover:bg-green-500/20 text-green-400 border border-green-500/30 px-3 py-1.5 rounded-lg transition-colors font-cairo disabled:opacity-40"
                    >
                      {sendingApproved ? (
                        <span className="w-3 h-3 border border-green-400 border-t-transparent rounded-full animate-spin" />
                      ) : (
                        <CheckCheck size={11} />
                      )}
                      إرسال الاقتراح ✓
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Manual input row — replaced by a notice when the number is disconnected. */}
          {selectedDisconnected ? (
            <div className="px-4 py-3 border-t border-gray-800 text-center text-xs text-gray-500 font-cairo">
              هذا الرقم غير متصل — يمكنك عرض السجل لكن لا يمكن إرسال رسائل جديدة. أعد ربط الرقم من صفحة واتساب للرد.
            </div>
          ) : recording ? (
            <div className="px-4 py-3 border-t border-gray-800 flex items-center gap-3">
              <button onClick={() => stopRecording(true)} title="إلغاء" className="text-gray-400 hover:text-red-400 transition-colors">
                <X size={18} />
              </button>
              <div className="flex-1 flex items-center gap-2 text-red-400">
                <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse" />
                <span className="text-sm font-mono">{Math.floor(recordSecs / 60)}:{String(recordSecs % 60).padStart(2, '0')}</span>
                <span className="text-xs text-gray-500 font-cairo">جارٍ التسجيل...</span>
              </div>
              <button onClick={() => stopRecording(false)} title="إرسال" className="w-10 h-10 rounded-xl bg-gradient-to-br from-gold-primary to-gold-dark text-gray-950 flex items-center justify-center hover:opacity-90 transition-all">
                <Send size={16} className="rotate-180" />
              </button>
            </div>
          ) : (
            <div className="px-4 py-3 border-t border-gray-800 flex gap-2 items-center relative">
              {/* Template quick-insert */}
              <div className="relative shrink-0">
                <button
                  onClick={() => setShowTemplates((s) => !s)}
                  title="إدراج قالب"
                  className="w-10 h-10 rounded-xl bg-gray-800 border border-gray-700 text-gray-400 hover:text-gold-primary flex items-center justify-center transition-colors"
                >
                  <FileText size={16} />
                </button>
                {showTemplates && (
                  <div className="absolute bottom-12 right-0 w-64 max-h-72 overflow-y-auto bg-gray-900 border border-gray-700 rounded-xl shadow-xl z-20 p-1">
                    {templates.filter((t) => t.channel === 'both' || t.channel === (selectedIsEmail ? 'email' : 'whatsapp')).length === 0 && (
                      <p className="text-xs text-gray-500 font-cairo p-3 text-center">لا توجد قوالب لهذه القناة</p>
                    )}
                    {templates
                      .filter((t) => t.channel === 'both' || t.channel === (selectedIsEmail ? 'email' : 'whatsapp'))
                      .map((t) => (
                        <button key={t.id} onClick={() => insertTemplate(t.body)}
                          className="w-full text-right px-3 py-2 rounded-lg hover:bg-gray-800 transition-colors">
                          <div className="text-sm text-white font-cairo truncate">{t.name}</div>
                          <div className="text-[11px] text-gray-500 font-cairo truncate">{renderTemplate(t.body, { name: selectedLead?.name || selectedConv?.contact_name || '', company: selectedLead?.company || '', industry: selectedLead?.industry || '', city: selectedLead?.city || '' })}</div>
                        </button>
                      ))}
                  </div>
                )}
              </div>
              {/* Attachments/voice are WhatsApp-only for now. */}
              {!selectedIsEmail && <>
                <input type="file" ref={fileInputRef} onChange={handleAttachFile} className="hidden" />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploadingMedia}
                  title="إرفاق ملف"
                  className="w-10 h-10 shrink-0 rounded-xl bg-gray-800 border border-gray-700 text-gray-400 hover:text-white flex items-center justify-center disabled:opacity-40 transition-colors"
                >
                  {uploadingMedia ? (
                    <span className="w-4 h-4 border-2 border-gray-500 border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <Paperclip size={16} />
                  )}
                </button>
              </>}
              <input
                type="text"
                value={msgInput}
                onChange={(e) => setMsgInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
                placeholder={selectedIsEmail ? 'اكتب ردك بالبريد...' : 'اكتب رسالتك...'}
                className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo"
              />
              {(msgInput.trim() || selectedIsEmail) ? (
                <button
                  onClick={handleSend}
                  disabled={sending || !msgInput.trim()}
                  className="w-10 h-10 shrink-0 rounded-xl bg-gradient-to-br from-gold-primary to-gold-dark text-gray-950 flex items-center justify-center hover:opacity-90 disabled:opacity-40 transition-all"
                >
                  {sending ? (
                    <span className="w-4 h-4 border-2 border-gray-950 border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <Send size={16} className="rotate-180" />
                  )}
                </button>
              ) : (
                <button
                  onClick={startRecording}
                  disabled={uploadingMedia}
                  title="تسجيل رسالة صوتية"
                  className="w-10 h-10 shrink-0 rounded-xl bg-gray-800 border border-gray-700 text-gray-400 hover:text-red-400 flex items-center justify-center disabled:opacity-40 transition-colors"
                >
                  <Mic size={16} />
                </button>
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-gray-600">
          <div className="text-center">
            <MessageSquare size={48} className="mx-auto mb-3 text-gray-700" />
            <p className="font-cairo">اختر محادثة لعرضها</p>
            <p className="text-sm text-gray-700 mt-1">Select a conversation</p>
          </div>
        </div>
      )}

      {showAction && selectedId && (
        <ActionModal
          conversationId={selectedId}
          onClose={() => setShowAction(false)}
          onDone={() => { mutateConvs(); mutateMsgs() }}
        />
      )}

      {composeOpen && (
        <ComposeModal
          onClose={() => setComposeOpen(false)}
          onSent={(cid) => {
            setComposeOpen(false)
            mutateConvs()
            if (cid) setSelectedId(cid)
          }}
        />
      )}
    </div>
  )
}
