'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import Link from 'next/link'
import { clsx } from 'clsx'
import toast from 'react-hot-toast'
import {
  LayoutDashboard,
  BarChart3,
  Users,
  MessageSquare,
  KanbanSquare,
  GitBranch,
  CalendarCheck,
  FileSpreadsheet,
  Megaphone,
  Smartphone,
  Mail,
  FileText,
  Settings,
  CreditCard,
  Bell,
  ChevronRight,
  LogOut,
  Menu,
  X,
  Bot,
  UserCog,
  Webhook,
  Activity,
  FlaskConical,
  Sparkles,
  ShieldCheck,
  Building2,
  UsersRound,
  ScrollText,
  SlidersHorizontal,
  Rocket,
  Globe,
} from 'lucide-react'
import { authApi, leadsApi, notificationsApi, onboardingApi } from '@/lib/api'
import type { AuthUser, Notification } from '@/lib/types'
import useSWR from 'swr'
import ThemeToggle from '@/components/theme-toggle'
import { LanguageProvider, useLang } from '@/lib/i18n'

interface NavItem {
  href: string
  label: string
  labelEn: string
  icon: React.ComponentType<{ size?: number; className?: string }>
  adminOnly?: boolean      // hidden from non-admin (agent) members; also route-guarded
  platformOnly?: boolean   // platform owner (is_admin) only — the cross-tenant console
}

interface NavGroup {
  label: string
  labelEn: string
  items: NavItem[]
}

// Grouped by the job the user is doing, in the order the product flows:
// find leads → talk to them → send outreach → configure channels → run the workspace.
const navGroups: NavGroup[] = [
  { label: 'نظرة عامة', labelEn: 'Overview', items: [
    { href: '/', label: 'الرئيسية', labelEn: 'Dashboard', icon: LayoutDashboard },
    { href: '/analytics', label: 'التحليلات', labelEn: 'Analytics', icon: BarChart3, adminOnly: true },
    { href: '/activity', label: 'نشاط المساعد الذكي', labelEn: 'AI Activity', icon: Sparkles, adminOnly: true },
  ] },
  { label: 'العملاء المحتملون', labelEn: 'Prospecting', items: [
    { href: '/leads', label: 'العملاء المحتملون', labelEn: 'Leads', icon: Users },
    { href: '/scrape', label: 'جمع البيانات', labelEn: 'Scrape', icon: Bot, adminOnly: true },
    { href: '/growth', label: 'النمو التلقائي', labelEn: 'Autonomous Growth', icon: Rocket, adminOnly: true },
    { href: '/site-factory', label: 'مصنع المواقع', labelEn: 'Site Factory', icon: Globe, adminOnly: true },
  ] },
  { label: 'المبيعات', labelEn: 'Sales', items: [
    { href: '/inbox', label: 'المحادثات', labelEn: 'Inbox', icon: MessageSquare },
    { href: '/pipeline', label: 'مسار المبيعات', labelEn: 'Pipeline', icon: KanbanSquare },
    { href: '/submissions', label: 'الطلبات والحجوزات', labelEn: 'Conversions', icon: CalendarCheck },
    { href: '/documents', label: 'المستندات', labelEn: 'Documents', icon: FileSpreadsheet },
  ] },
  { label: 'التواصل', labelEn: 'Outreach', items: [
    { href: '/campaigns', label: 'الحملات', labelEn: 'Campaigns', icon: Megaphone, adminOnly: true },
    { href: '/sequences', label: 'رسائل المتابعة', labelEn: 'Sequences', icon: GitBranch, adminOnly: true },
    { href: '/templates', label: 'القوالب', labelEn: 'Templates', icon: FileText },
    { href: '/ab-tests', label: 'اختبارات A/B', labelEn: 'A/B Tests', icon: FlaskConical, adminOnly: true },
  ] },
  { label: 'القنوات', labelEn: 'Channels', items: [
    { href: '/instances', label: 'أرقام واتساب', labelEn: 'WhatsApp', icon: Smartphone, adminOnly: true },
    { href: '/email-accounts', label: 'حسابات البريد', labelEn: 'Email', icon: Mail, adminOnly: true },
  ] },
  { label: 'مساحة العمل', labelEn: 'Workspace', items: [
    { href: '/team', label: 'الفريق', labelEn: 'Team', icon: UserCog, adminOnly: true },
    { href: '/settings', label: 'الإعدادات', labelEn: 'Settings', icon: Settings, adminOnly: true },
    { href: '/billing', label: 'الاشتراك والفوترة', labelEn: 'Billing', icon: CreditCard, adminOnly: true },
    { href: '/webhooks', label: 'التكاملات (Webhooks)', labelEn: 'Webhooks', icon: Webhook, adminOnly: true },
    { href: '/monitoring', label: 'المراقبة', labelEn: 'Monitoring', icon: Activity, adminOnly: true },
  ] },
  // Platform owner console (is_admin) — cross-tenant.
  { label: 'إدارة المنصة', labelEn: 'Platform', items: [
    { href: '/admin', label: 'لوحة المالك', labelEn: 'Platform', icon: ShieldCheck, platformOnly: true },
    { href: '/admin/companies', label: 'الشركات', labelEn: 'Companies', icon: Building2, platformOnly: true },
    { href: '/admin/accounts', label: 'الحسابات', labelEn: 'Accounts', icon: UsersRound, platformOnly: true },
    { href: '/admin/system', label: 'صحة النظام', labelEn: 'System', icon: Activity, platformOnly: true },
    { href: '/admin/audit', label: 'سجل الإجراءات', labelEn: 'Audit', icon: ScrollText, platformOnly: true },
    { href: '/admin/config', label: 'حدود الخطط', labelEn: 'Plan limits', icon: SlidersHorizontal, platformOnly: true },
  ] },
]

const navItems: NavItem[] = navGroups.flatMap((g) => g.items)

function useAuth() {
  const router = useRouter()
  const { data, error } = useSWR('/auth/me', () => authApi.me().then((r) => r.data), {
    revalidateOnFocus: false,
    onError: () => {
      localStorage.removeItem('auth_token')
      router.push('/login')
    },
  })
  return { user: data as AuthUser | undefined, error }
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  // Provide the language context to the whole dashboard, then render the shell (which
  // consumes it). The provider must sit above the consumer, hence this thin wrapper.
  return (
    <LanguageProvider>
      <DashboardShell>{children}</DashboardShell>
    </LanguageProvider>
  )
}

function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const { user } = useAuth()
  const { lang } = useLang()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [notifOpen, setNotifOpen] = useState(false)
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [unreadNotifCount, setUnreadNotifCount] = useState(0)
  const [impersonating, setImpersonating] = useState<string | null>(null)

  useEffect(() => {
    if (typeof window !== 'undefined') setImpersonating(localStorage.getItem('imp_company'))
  }, [pathname])

  function exitImpersonation() {
    const owner = localStorage.getItem('owner_token')
    if (owner) localStorage.setItem('auth_token', owner)
    localStorage.removeItem('owner_token')
    localStorage.removeItem('imp_company')
    window.location.href = '/admin/companies'   // full reload → re-fetch as owner
  }

  // Onboarding redirect: send to the wizard only if onboarding truly isn't done.
  // The local flag is a fast path; when it's missing (e.g. the user cleared browser
  // data) we confirm against the server's onboarding_done before trapping them — so a
  // fully set-up tenant is never forced back into onboarding.
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (pathname === '/onboarding') return
    if (!user) return
    if (localStorage.getItem('qualifay_onboarding_done')) return
    onboardingApi.profile()
      .then((r) => {
        if (r.data?.onboarding_done) {
          localStorage.setItem('qualifay_onboarding_done', '1')  // self-heal the flag
        } else {
          router.push('/onboarding')
        }
      })
      .catch(() => { /* on error, don't trap the user on onboarding */ })
  }, [user, pathname, router])

  const fetchNotifications = useCallback(async () => {
    try {
      const res = await notificationsApi.list({ unread_only: true })
      // The API returns a bare array (unread-first); tolerate a wrapped shape too.
      const items: Notification[] = Array.isArray(res.data) ? res.data : (res.data?.items || [])
      setNotifications(items)
      setUnreadNotifCount(items.filter((n) => !n.read_at && !n.read).length)
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    fetchNotifications()
    const interval = setInterval(fetchNotifications, 30000)
    return () => clearInterval(interval)
  }, [fetchNotifications])

  // Where a notification points: an explicit link, or a chat / lead in its data payload.
  const notifHref = (n: Notification): string | null => {
    const d = (n.data || {}) as Record<string, unknown>
    if (typeof d.link === 'string') return d.link
    if (typeof d.conversation_id === 'string') return `/inbox?conversation=${d.conversation_id}`
    if (typeof d.lead_id === 'string') return `/inbox?lead=${d.lead_id}`
    return null
  }

  const handleNotifClick = (n: Notification) => {
    const href = notifHref(n)
    notificationsApi.markRead(n.id).catch(() => {})
    setNotifOpen(false)
    fetchNotifications()
    if (!href) return
    const convId = (n.data as Record<string, unknown>)?.conversation_id
    // Already on the inbox? router.push won't re-run its mount effect — nudge it directly.
    if (typeof convId === 'string' && pathname.startsWith('/inbox')) {
      window.history.pushState({}, '', href)
      window.dispatchEvent(new CustomEvent('qualifay:selectConversation', { detail: convId }))
    } else {
      router.push(href)
    }
  }

  async function handleLogout() {
    try {
      await authApi.logout()
    } catch {
      // ignore
    }
    localStorage.removeItem('auth_token')
    toast.success('تم تسجيل الخروج')
    router.push('/login')
  }

  const isActive = (href: string) => {
    if (href === '/') return pathname === '/'
    return pathname.startsWith(href)
  }

  // Role-based access: agents (non-admin) only see operational pages; config/billing/team
  // are tenant-admin-only; the owner console is platform-admin (is_admin) only. Backend
  // enforces all of this too — the UI just avoids dead ends.
  const isAdmin = !!user?.is_tenant_admin
  const isPlatform = !!user?.is_admin
  const canSee = (i: NavItem) => (i.platformOnly ? isPlatform : true) && (i.adminOnly ? isAdmin : true)
  const visibleGroups = navGroups
    .map((g) => ({ ...g, items: g.items.filter(canSee) }))
    .filter((g) => g.items.length > 0)

  // The most specific nav entry for the current page (so /admin/companies doesn't match /admin).
  const current = navItems
    .filter((i) => isActive(i.href))
    .sort((a, b) => b.href.length - a.href.length)[0]

  // Leads waiting for a human decision — the core "human in the loop" step, so it's badged.
  const { data: leadStats } = useSWR(user ? '/leads/stats' : null,
    () => leadsApi.stats().then((r) => r.data), { refreshInterval: 60000 })
  const pendingCount: number = leadStats?.pending_review || 0

  // Close the notifications panel on outside click / Escape.
  const notifRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!notifOpen) return
    const onDown = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) setNotifOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setNotifOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [notifOpen])

  // Guard: bounce anyone who directly hits a route their role can't access.
  useEffect(() => {
    if (!user) return
    // Platform console: platform admins only.
    if (pathname.startsWith('/admin') && !isPlatform) { router.replace('/'); return }
    if (isAdmin) return
    const hit = navItems.find((i) => i.adminOnly && i.href !== '/' && pathname.startsWith(i.href))
    if (hit) router.replace('/')
  }, [user, isAdmin, isPlatform, pathname, router])

  return (
    <div className="flex h-screen bg-gray-950 overflow-hidden">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/60 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={clsx(
          'fixed inset-y-0 right-0 z-30 w-64 bg-gray-900 border-l border-gray-800 flex flex-col transition-transform duration-300 lg:static lg:translate-x-0',
          sidebarOpen ? 'translate-x-0' : 'translate-x-full lg:translate-x-0'
        )}
      >
        {/* Logo */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-gold-primary to-gold-dark flex items-center justify-center text-gray-950 font-bold text-sm">
              Q
            </div>
            <span className="font-bold text-white font-cairo text-lg">Qualifay</span>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden text-gray-400 hover:text-white"
          >
            <X size={18} />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto px-3 py-3 space-y-4" aria-label={lang === 'en' ? 'Main' : 'التنقل الرئيسي'}>
          {visibleGroups.map((group) => (
            <div key={group.labelEn}>
              <div className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-wide text-gray-500 font-cairo">
                {lang === 'en' ? group.labelEn : group.label}
              </div>
              <div className="space-y-0.5">
                {group.items.map((item) => {
                  const Icon = item.icon
                  const active = current?.href === item.href
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setSidebarOpen(false)}
                      aria-current={active ? 'page' : undefined}
                      className={clsx(
                        'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-cairo transition-colors duration-150 group',
                        active
                          ? 'bg-gold-primary/10 text-gold-primary font-semibold'
                          : 'text-gray-400 hover:text-white hover:bg-gray-800'
                      )}
                    >
                      <Icon
                        size={17}
                        className={clsx('shrink-0', active ? 'text-gold-primary' : 'text-gray-500 group-hover:text-white')}
                      />
                      <span className="flex-1 min-w-0 truncate">{lang === 'en' ? item.labelEn : item.label}</span>
                      {item.href === '/leads' && pendingCount > 0 && (
                        <span
                          title={lang === 'en' ? 'Waiting for your review' : 'بانتظار مراجعتك'}
                          className="text-[11px] bg-gold-primary text-gray-950 font-bold px-1.5 py-0.5 rounded-full min-w-[20px] text-center"
                        >
                          {pendingCount > 99 ? '99+' : pendingCount}
                        </span>
                      )}
                    </Link>
                  )
                })}
              </div>
            </div>
          ))}
        </nav>

        {/* User */}
        {user && (
          <div className="px-3 py-3 border-t border-gray-800">
            <div className="flex items-center gap-3 px-2 py-2 rounded-lg">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-gold-primary to-gold-dark flex items-center justify-center text-gray-950 font-bold text-xs">
                {user.name?.charAt(0) || 'U'}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-white truncate font-cairo">{user.name}</div>
                <div className="text-xs text-gray-500 truncate">{user.tenant?.name}</div>
              </div>
              <button
                onClick={handleLogout}
                title="تسجيل الخروج"
                className="text-gray-500 hover:text-red-400 transition-colors"
              >
                <LogOut size={16} />
              </button>
            </div>
          </div>
        )}
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <header className="bg-gray-900 border-b border-gray-800 px-4 py-3 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(true)}
              className="lg:hidden text-gray-400 hover:text-white"
            >
              <Menu size={20} />
            </button>
            {/* Where am I: section › page, so deep pages are never anonymous. */}
            <nav aria-label="breadcrumb" className="flex items-center gap-1.5 text-sm font-cairo min-w-0">
              <span className="hidden sm:inline text-gray-500 truncate">{user?.tenant?.name || 'Qualifay'}</span>
              {current && (
                <>
                  <ChevronRight size={14} className="hidden sm:inline text-gray-600 rtl:rotate-180 shrink-0" />
                  <span className="font-semibold text-white truncate">{lang === 'en' ? current.labelEn : current.label}</span>
                </>
              )}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            <ThemeToggle />
            {/* Notifications */}
            <div className="relative" ref={notifRef}>
              <button
                onClick={() => setNotifOpen((v) => !v)}
                aria-label={lang === 'en' ? 'Notifications' : 'الإشعارات'}
                aria-expanded={notifOpen}
                className="relative p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
              >
                <Bell size={18} />
                {unreadNotifCount > 0 && (
                  <span className="absolute top-1 right-1 w-4 h-4 bg-gold-primary rounded-full text-[10px] font-bold text-gray-950 flex items-center justify-center">
                    {unreadNotifCount > 9 ? '9+' : unreadNotifCount}
                  </span>
                )}
              </button>

              {notifOpen && (
                <div className="absolute left-0 top-full mt-2 w-80 bg-gray-900 border border-gray-800 rounded-xl shadow-2xl z-50">
                  <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
                    <span className="font-semibold text-white font-cairo text-sm">الإشعارات</span>
                    <button
                      onClick={async () => {
                        await notificationsApi.markAllRead()
                        setUnreadNotifCount(0)
                        setNotifOpen(false)
                      }}
                      className="text-xs text-gold-primary hover:text-gold-dark"
                    >
                      تحديد الكل كمقروء
                    </button>
                  </div>
                  <div className="max-h-72 overflow-y-auto divide-y divide-gray-800">
                    {notifications.length === 0 ? (
                      <p className="text-center text-gray-500 py-6 text-sm font-cairo">لا توجد إشعارات</p>
                    ) : (
                      notifications.map((n) => {
                        const href = notifHref(n)
                        return (
                          <div
                            key={n.id}
                            onClick={() => handleNotifClick(n)}
                            className={clsx(
                              'px-4 py-3 hover:bg-gray-800 transition-colors',
                              href && 'cursor-pointer'
                            )}
                          >
                            <p className="text-sm text-white font-cairo">{n.title}</p>
                            <p className="text-xs text-gray-400 mt-0.5 whitespace-pre-wrap">{n.message || n.body}</p>
                          </div>
                        )
                      })
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Plan badge */}
            {user?.tenant?.plan && (
              <span className="hidden sm:inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold bg-gold-primary/10 text-gold-primary border border-gold-primary/20 capitalize">
                {user.tenant.plan}
              </span>
            )}
          </div>
        </header>

        {/* Impersonation banner — visible while the owner is "viewing as" a company. */}
        {impersonating && (
          <div className="bg-gold-primary text-gray-950 px-4 py-2 flex items-center justify-center gap-3 text-sm font-cairo shrink-0">
            <span>أنت تتصفّح كـ <b>{impersonating}</b> (وضع المالك)</span>
            <button onClick={exitImpersonation} className="underline font-semibold">العودة لحساب المالك ←</button>
          </div>
        )}

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-4 lg:p-6">
          {children}
        </main>
      </div>
    </div>
  )
}
