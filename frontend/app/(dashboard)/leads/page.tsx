'use client'

import { useState, useCallback, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import Link from 'next/link'
import { Search, RefreshCw, CheckCheck, Filter } from 'lucide-react'
import { leadsApi, templatesApi } from '@/lib/api'
import type { Lead, LeadStage, LeadSource } from '@/lib/types'
import LeadReviewCard from '@/components/LeadReviewCard'

type Tab = 'review' | 'all' | 'pool'

const STAGE_LABELS: Record<string, string> = {
  new: 'جديد', pending_review: 'قيد المراجعة', approved: 'مقبول',
  rejected: 'مرفوض', manual: 'يدوي', outreach: 'تواصل',
  replied: 'استجاب', booked: 'محجوز', won: 'مربوح',
  lost: 'خسارة', archived: 'مؤرشف',
}

// How a lead can be reached — drives the badge in the table so you know, per lead,
// whether it's contactable and via which channel, before approving it for outreach.
const REACH: Record<string, { label: string; cls: string }> = {
  whatsapp:    { label: 'واتساب ✓',      cls: 'text-wa-green bg-wa-green/10 border border-wa-green/25' },
  phone:       { label: 'هاتف',          cls: 'text-blue-400 bg-blue-500/10 border border-blue-500/25' },
  phone_no_wa: { label: 'ليس على واتساب', cls: 'text-amber-400 bg-amber-500/10 border border-amber-500/25' },
  email:       { label: 'بريد',          cls: 'text-purple-400 bg-purple-500/10 border border-purple-500/25' },
  none:        { label: 'يحتاج إثراء',    cls: 'text-gray-500 bg-gray-700/40 border border-gray-600' },
}

function ReachBadge({ reach }: { reach?: string }) {
  const r = REACH[reach || 'none'] || REACH.none
  return <span className={`text-[11px] px-1.5 py-0.5 rounded font-cairo whitespace-nowrap ${r.cls}`}>{r.label}</span>
}

export default function LeadsPage() {
  return (
    <Suspense fallback={<div className="flex justify-center py-12"><div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" /></div>}>
      <LeadsContent />
    </Suspense>
  )
}

function LeadsContent() {
  const searchParams = useSearchParams()
  const initialTab = (searchParams.get('tab') as Tab) || 'review'
  const [tab, setTab] = useState<Tab>(initialTab)

  // Review queue
  const { data: reviewData, mutate: mutateReview, isLoading: reviewLoading } = useSWR(
    'leads/review-queue',
    () => leadsApi.reviewQueue().then((r) => r.data),
    { revalidateOnFocus: true }
  )
  const reviewLeads: Lead[] = reviewData?.leads || []

  // All leads filters
  const [search, setSearch] = useState('')
  const [stageFilter, setStageFilter] = useState<string>('')
  const [sourceFilter, setSourceFilter] = useState<string>('')
  const [minScore, setMinScore] = useState<string>('')
  const [page, setPage] = useState(1)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [outreachTemplate, setOutreachTemplate] = useState<string>('')
  const { data: tplData } = useSWR('templates', () => templatesApi.list().then((r) => r.data))
  const templates: { id: string; name: string }[] = Array.isArray(tplData) ? tplData : []

  const allLeadsKey = tab === 'all' ? ['leads/all', search, stageFilter, sourceFilter, minScore, page] : null
  const { data: allData, isLoading: allLoading, mutate: mutateAll } = useSWR(
    allLeadsKey,
    () => leadsApi.list({
      search: search || undefined,
      stage: stageFilter || undefined,
      source: sourceFilter || undefined,
      min_score: minScore ? Number(minScore) : undefined,
      page,
      per_page: 20,
    }).then((r) => r.data)
  )
  const allLeads: Lead[] = allData?.leads || []

  // Pool
  const [poolSearch, setPoolSearch] = useState('')
  const [poolIndustry, setPoolIndustry] = useState('')
  const [poolCity, setPoolCity] = useState('')
  const poolKey = tab === 'pool' ? ['leads/pool', poolIndustry, poolCity] : null
  const { data: poolData, mutate: mutatePool, isLoading: poolLoading } = useSWR(
    poolKey,
    () => leadsApi.poolSearch({ industry: poolIndustry || undefined, city: poolCity || undefined }).then((r) => r.data)
  )
  const poolLeads: Lead[] = Array.isArray(poolData) ? poolData : (poolData?.items || poolData?.leads || [])

  const handleApprove = useCallback(async (id: string) => {
    try {
      await leadsApi.approve(id)
      toast.success('تم قبول العميل المحتمل')
      mutateReview()
    } catch { toast.error('فشل قبول العميل') }
  }, [mutateReview])

  const handleReject = useCallback(async (id: string, reason?: string) => {
    try {
      await leadsApi.reject(id, reason)
      toast.success('تم رفض العميل المحتمل')
      mutateReview()
    } catch { toast.error('فشل رفض العميل') }
  }, [mutateReview])

  const handleTakeManually = useCallback(async (id: string) => {
    try {
      await leadsApi.takeManually(id)
      toast.success('تم نقل العميل للمعالجة اليدوية')
      mutateReview()
    } catch { toast.error('فشل العملية') }
  }, [mutateReview])

  const handleBulkApprove = useCallback(async () => {
    if (reviewLeads.length === 0) return
    const ids = reviewLeads.map((l) => l.id)
    try {
      await leadsApi.bulkApprove(ids)
      toast.success(`تم قبول ${ids.length} عميل محتمل`)
      mutateReview()
    } catch { toast.error('فشل القبول الجماعي') }
  }, [reviewLeads, mutateReview])

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const n = new Set(prev)
      n.has(id) ? n.delete(id) : n.add(id)
      return n
    })
  }, [])

  const toggleSelectAll = useCallback(() => {
    setSelectedIds((prev) => prev.size === allLeads.length ? new Set() : new Set(allLeads.map((l) => l.id)))
  }, [allLeads])

  const handleBulkApproveSelected = useCallback(async () => {
    const ids = Array.from(selectedIds)
    if (!ids.length) return
    try {
      await leadsApi.bulkApprove(ids, outreachTemplate || undefined)
      toast.success(`تم قبول ${ids.length} عميل وبدء التواصل`)
      setSelectedIds(new Set())
    } catch { toast.error('فشل القبول الجماعي') }
  }, [selectedIds, outreachTemplate])

  const [enriching, setEnriching] = useState(false)
  const handleEnrichLinkedIn = useCallback(async () => {
    setEnriching(true)
    try {
      const res = await leadsApi.enrichLinkedIn()
      const d = res.data || {}
      if ((d.queued ?? 0) > 0) {
        toast.success(`تم جدولة إثراء ${d.queued} عميل — ستُملأ بيانات الاتصال عبر الإضافة`)
      } else {
        toast('لا يوجد عملاء LinkedIn بحاجة لإثراء', { icon: 'ℹ️' })
      }
    } catch {
      toast.error('فشل جدولة الإثراء')
    } finally {
      setEnriching(false)
    }
  }, [])

  const [checkingReach, setCheckingReach] = useState(false)
  const handleCheckReachability = useCallback(async (ids?: string[]) => {
    setCheckingReach(true)
    try {
      const res = await leadsApi.checkReachability(ids && ids.length ? ids : undefined)
      const d = res.data || {}
      toast.success(`تم الفحص: ${d.reachable ?? 0} على واتساب، ${d.not_reachable ?? 0} غير متاح`)
      mutateAll()
      setSelectedIds(new Set())
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(err?.response?.data?.detail || 'فشل فحص واتساب')
    } finally {
      setCheckingReach(false)
    }
  }, [])

  const handlePoolClaim = useCallback(async (id: string) => {
    try {
      await leadsApi.poolClaim(id)
      toast.success('تم استلام العميل من المجمّع')
      mutatePool()
    } catch { toast.error('فشل الاستلام') }
  }, [mutatePool])

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white font-cairo">العملاء المحتملون</h1>
        <p className="text-gray-400 text-sm mt-1">Leads Management</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-900 border border-gray-800 rounded-xl p-1 w-fit">
        {([
          { key: 'review', label: 'طابور المراجعة', badge: reviewLeads.length },
          { key: 'all', label: 'كل العملاء' },
          { key: 'pool', label: 'المجمّع' },
        ] as { key: Tab; label: string; badge?: number }[]).map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={clsx(
              'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all font-cairo',
              tab === t.key
                ? 'bg-gold-primary text-gray-950 font-semibold'
                : 'text-gray-400 hover:text-white'
            )}
          >
            {t.label}
            {t.badge !== undefined && t.badge > 0 && (
              <span className={clsx(
                'text-xs px-1.5 py-0.5 rounded-full font-bold',
                tab === t.key ? 'bg-gray-950/30 text-gray-950' : 'bg-gold-primary/10 text-gold-primary'
              )}>
                {t.badge}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Review Queue */}
      {tab === 'review' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-gray-400 text-sm font-cairo">
              {reviewLeads.length} عميل بانتظار المراجعة
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => mutateReview()}
                className="flex items-center gap-1.5 text-gray-400 hover:text-white text-sm px-3 py-1.5 rounded-lg border border-gray-700 hover:border-gray-600 transition-colors"
              >
                <RefreshCw size={14} />
                <span className="font-cairo">تحديث</span>
              </button>
              {reviewLeads.length > 1 && (
                <button
                  onClick={handleBulkApprove}
                  className="flex items-center gap-1.5 bg-green-500/10 hover:bg-green-500/20 text-green-400 border border-green-500/30 text-sm px-3 py-1.5 rounded-lg transition-colors font-cairo"
                >
                  <CheckCheck size={14} />
                  قبول الكل ({reviewLeads.length})
                </button>
              )}
            </div>
          </div>

          {reviewLoading ? (
            <div className="flex justify-center py-12">
              <div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" />
            </div>
          ) : reviewLeads.length === 0 ? (
            <div className="text-center py-16 text-gray-500">
              <CheckCheck size={40} className="mx-auto mb-3 text-gray-700" />
              <p className="font-cairo">لا يوجد عملاء بانتظار المراجعة</p>
              <p className="text-xs text-gray-600 mt-1">All caught up!</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {reviewLeads.map((lead) => (
                <LeadReviewCard
                  key={lead.id}
                  lead={lead}
                  onApprove={handleApprove}
                  onReject={handleReject}
                  onTakeManually={handleTakeManually}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* All Leads */}
      {tab === 'all' && (
        <div className="space-y-4">
          {/* Filters */}
          <div className="flex flex-wrap gap-3">
            <div className="relative flex-1 min-w-[200px]">
              <Search size={15} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                placeholder="بحث باسم الشركة أو البريد..."
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(1) }}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg pr-9 pl-4 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo"
              />
            </div>
            <select
              value={stageFilter}
              onChange={(e) => { setStageFilter(e.target.value); setPage(1) }}
              className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo"
            >
              <option value="">كل المراحل</option>
              {Object.entries(STAGE_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
            <input
              type="number"
              placeholder="أدنى نتيجة"
              value={minScore}
              onChange={(e) => { setMinScore(e.target.value); setPage(1) }}
              min={0} max={100}
              className="w-28 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-gold-primary"
            />
            <button
              onClick={() => handleCheckReachability()}
              disabled={checkingReach}
              title="التحقق من أرقام واتساب لكل العملاء غير المفحوصين"
              className="flex items-center gap-1.5 bg-wa-green/10 hover:bg-wa-green/20 text-wa-green border border-wa-green/30 text-sm px-3 py-2 rounded-lg transition-colors font-cairo disabled:opacity-50"
            >
              {checkingReach ? <RefreshCw size={14} className="animate-spin" /> : null}
              فحص واتساب للكل
            </button>
            <button
              onClick={handleEnrichLinkedIn}
              disabled={enriching}
              title="فتح ملفات LinkedIn غير المكتملة عبر الإضافة لجلب الهاتف/البريد"
              className="flex items-center gap-1.5 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 border border-blue-500/30 text-sm px-3 py-2 rounded-lg transition-colors font-cairo disabled:opacity-50"
            >
              {enriching ? <RefreshCw size={14} className="animate-spin" /> : null}
              إثراء LinkedIn
            </button>
          </div>

          {/* Bulk action bar — appears when leads are selected. */}
          {selectedIds.size > 0 && (
            <div className="flex items-center justify-between bg-gold-primary/10 border border-gold-primary/30 rounded-lg px-4 py-2.5">
              <span className="text-sm text-gold-primary font-cairo">تم اختيار {selectedIds.size} عميل</span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setSelectedIds(new Set())}
                  className="text-xs text-gray-400 hover:text-white px-3 py-1.5 rounded-lg border border-gray-700 transition-colors font-cairo"
                >
                  إلغاء التحديد
                </button>
                <button
                  onClick={() => handleCheckReachability(Array.from(selectedIds))}
                  disabled={checkingReach}
                  className="flex items-center gap-1.5 bg-wa-green/10 hover:bg-wa-green/20 text-wa-green border border-wa-green/30 text-sm px-3 py-1.5 rounded-lg transition-colors font-cairo disabled:opacity-50"
                >
                  فحص واتساب
                </button>
                <select
                  value={outreachTemplate}
                  onChange={(e) => setOutreachTemplate(e.target.value)}
                  title="اختر قالباً أو اترك للذكاء الاصطناعي"
                  className="text-xs bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-gray-200 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo"
                >
                  <option value="">✨ ذكاء اصطناعي</option>
                  {templates.map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
                <button
                  onClick={handleBulkApproveSelected}
                  className="flex items-center gap-1.5 bg-green-500/15 hover:bg-green-500/25 text-green-400 border border-green-500/30 text-sm px-3 py-1.5 rounded-lg transition-colors font-cairo font-semibold"
                >
                  <CheckCheck size={14} />
                  قبول وتواصل ({selectedIds.size})
                </button>
              </div>
            </div>
          )}

          {allLoading ? (
            <div className="flex justify-center py-12">
              <div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-800">
                    <th className="px-3 py-3 w-8">
                      <input
                        type="checkbox"
                        checked={allLeads.length > 0 && selectedIds.size === allLeads.length}
                        onChange={toggleSelectAll}
                        className="accent-gold-primary cursor-pointer"
                        title="تحديد الكل"
                      />
                    </th>
                    <th className="text-right px-4 py-3 text-xs font-semibold text-gray-400 font-cairo">الشركة</th>
                    <th className="text-right px-4 py-3 text-xs font-semibold text-gray-400 font-cairo">المجال</th>
                    <th className="text-right px-4 py-3 text-xs font-semibold text-gray-400 font-cairo">المدينة</th>
                    <th className="text-right px-4 py-3 text-xs font-semibold text-gray-400 font-cairo">النتيجة</th>
                    <th className="text-right px-4 py-3 text-xs font-semibold text-gray-400 font-cairo">التواصل</th>
                    <th className="text-right px-4 py-3 text-xs font-semibold text-gray-400 font-cairo">المرحلة</th>
                    <th className="text-right px-4 py-3 text-xs font-semibold text-gray-400 font-cairo">المصدر</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {allLeads.map((lead) => (
                    <tr key={lead.id} className={clsx('hover:bg-gray-800/50 transition-colors', selectedIds.has(lead.id) && 'bg-gold-primary/5')}>
                      <td className="px-3 py-3">
                        <input
                          type="checkbox"
                          checked={selectedIds.has(lead.id)}
                          onChange={() => toggleSelect(lead.id)}
                          className="accent-gold-primary cursor-pointer"
                        />
                      </td>
                      <td className="px-4 py-3">
                        <Link href={`/leads/${lead.id}`} className="text-white font-cairo hover:text-gold-primary transition-colors underline-offset-2 hover:underline">
                          {lead.company || lead.name || '—'}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-gray-400 font-cairo">{lead.industry || '—'}</td>
                      <td className="px-4 py-3 text-gray-400 font-cairo">{lead.city || '—'}</td>
                      <td className="px-4 py-3">
                        {lead.bant_score !== undefined ? (
                          <span className={clsx(
                            'font-bold text-xs px-2 py-0.5 rounded',
                            lead.bant_score >= 70 ? 'text-green-400 bg-green-500/10'
                              : lead.bant_score >= 50 ? 'text-yellow-400 bg-yellow-500/10'
                              : 'text-red-400 bg-red-500/10'
                          )}>
                            {lead.bant_score}
                          </span>
                        ) : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <ReachBadge reach={lead.reach} />
                      </td>
                      <td className="px-4 py-3 text-gray-400 font-cairo">
                        {STAGE_LABELS[lead.stage] || lead.stage}
                      </td>
                      <td className="px-4 py-3 text-gray-500 text-xs">{lead.source}</td>
                    </tr>
                  ))}
                  {allLeads.length === 0 && (
                    <tr>
                      <td colSpan={8} className="text-center py-10 text-gray-500 font-cairo">
                        لا توجد نتائج
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
              {/* Pagination */}
              {allData?.pages > 1 && (
                <div className="flex justify-center gap-2 py-3 border-t border-gray-800">
                  <button
                    disabled={page === 1}
                    onClick={() => setPage((p) => p - 1)}
                    className="px-3 py-1.5 rounded-lg text-sm bg-gray-800 text-gray-300 disabled:opacity-40 hover:bg-gray-700 transition-colors"
                  >
                    السابق
                  </button>
                  <span className="text-sm text-gray-400 flex items-center font-cairo">
                    {page} / {allData.pages}
                  </span>
                  <button
                    disabled={page === allData.pages}
                    onClick={() => setPage((p) => p + 1)}
                    className="px-3 py-1.5 rounded-lg text-sm bg-gray-800 text-gray-300 disabled:opacity-40 hover:bg-gray-700 transition-colors"
                  >
                    التالي
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Pool */}
      {tab === 'pool' && (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-3">
            <input
              type="text"
              placeholder="المجال / Industry"
              value={poolIndustry}
              onChange={(e) => setPoolIndustry(e.target.value)}
              className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo"
            />
            <input
              type="text"
              placeholder="المدينة / City"
              value={poolCity}
              onChange={(e) => setPoolCity(e.target.value)}
              className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-gold-primary font-cairo"
            />
          </div>

          {poolLoading ? (
            <div className="flex justify-center py-12">
              <div className="w-8 h-8 border-2 border-gold-primary border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {poolLeads.map((lead) => (
                <div key={lead.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-semibold text-white font-cairo">{lead.company || lead.name}</h3>
                      <p className="text-sm text-gray-400 font-cairo">{lead.industry} · {lead.city}</p>
                    </div>
                    {lead.bant_score !== undefined && (
                      <span className={clsx(
                        'text-sm font-bold px-2 py-0.5 rounded',
                        lead.bant_score >= 70 ? 'text-green-400 bg-green-500/10'
                          : lead.bant_score >= 50 ? 'text-yellow-400 bg-yellow-500/10'
                          : 'text-red-400 bg-red-500/10'
                      )}>
                        {lead.bant_score}
                      </span>
                    )}
                  </div>
                  <button
                    onClick={() => handlePoolClaim(lead.id)}
                    className="w-full bg-gold-primary/10 hover:bg-gold-primary/20 text-gold-primary border border-gold-primary/30 rounded-lg py-2 text-sm font-semibold transition-colors font-cairo"
                  >
                    استلام العميل
                  </button>
                </div>
              ))}
              {poolLeads.length === 0 && (
                <div className="col-span-full text-center py-12 text-gray-500 font-cairo">
                  ابحث عن عملاء في المجمّع
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
