'use client'

// Opt out of static prerendering. This is an auth-gated, client-rendered page, so a
// build-time prerender adds nothing — and it trips a Next.js route-group bug
// ("Expected clientReferenceManifest to be defined") that fails the whole build. That
// failure was silently swallowed by the Dockerfile, shipping a stale dashboard.
export const dynamic = 'force-dynamic'

import useSWR from 'swr'
import Link from 'next/link'
import { clsx } from 'clsx'
import {
  Users, MessageSquare, Megaphone, CheckCircle, Search, Smartphone, Mail,
  KanbanSquare, FileText, GitBranch, Sparkles, FlaskConical, BarChart3,
  UserCog, Webhook, CalendarCheck, Settings, CreditCard, Rocket, ArrowLeft,
} from 'lucide-react'
import { dashboardApi } from '@/lib/api'
import type { DashboardStats } from '@/lib/types'

type Icon = React.ComponentType<{ size?: number; className?: string }>

interface Feature {
  href: string
  icon: Icon
  title: string
  en: string
  desc: string
  how: string
  step?: number
}

interface Group {
  title: string
  en: string
  icon: Icon
  accent: string
  items: Feature[]
}

const GROUPS: Group[] = [
  {
    title: 'ابدأ من هنا', en: 'Get started', icon: Rocket, accent: 'text-gold-primary',
    items: [
      { step: 1, href: '/instances', icon: Smartphone, title: 'اربط واتساب', en: 'Connect WhatsApp',
        desc: 'اربط رقم واتساب لإرسال واستقبال الرسائل. يبدأ الرقم بالإحماء تدريجياً لحماية حسابك من الحظر.',
        how: 'اضغط «إضافة نسخة» ثم امسح رمز QR من تطبيق واتساب على هاتفك.' },
      { step: 2, href: '/email-accounts', icon: Mail, title: 'اربط البريد', en: 'Connect email',
        desc: 'اربط بريدك (IMAP/SMTP) لاستقبال وإرسال الإيميلات داخل صندوق الوارد نفسه.',
        how: 'أدخل بيانات SMTP/IMAP لمزوّدك (مثل Hostinger أو Gmail).' },
      { step: 3, href: '/scrape', icon: Search, title: 'اجمع العملاء', en: 'Find leads',
        desc: 'اجمع عملاء محتملين آلياً من 9 مصادر: خرائط جوجل، لينكدإن، أبولو، الأدلة، المناقصات والمزيد.',
        how: 'اختر المصدر، حدّد المجال والمدينة، ثم اضغط «ابدأ».' },
    ],
  },
  {
    title: 'إدارة العملاء', en: 'Leads & pipeline', icon: Users, accent: 'text-blue-400',
    items: [
      { href: '/leads', icon: Users, title: 'العملاء المحتملون', en: 'Leads',
        desc: 'كل عملائك مع تقييم BANT ومصدرهم. الذكاء يؤهّلهم وأنت تقرّر مع من تتواصل.',
        how: 'في «طابور المراجعة»: وافق للتواصل / ارفض / تولَّ يدوياً.' },
      { href: '/pipeline', icon: KanbanSquare, title: 'خط الأنابيب', en: 'Pipeline',
        desc: 'لوحة مراحل الصفقات من «وارد» حتى «مربوح». تنقّل عملاءك عبر رحلة البيع بصرياً.',
        how: 'اسحب البطاقات بين الأعمدة لتغيير المرحلة، أو اضغط أي بطاقة لفتح محادثتها.' },
    ],
  },
  {
    title: 'التواصل', en: 'Communication', icon: MessageSquare, accent: 'text-wa-green',
    items: [
      { href: '/inbox', icon: MessageSquare, title: 'صندوق الوارد', en: 'Inbox',
        desc: 'محادثات واتساب والبريد في مكان واحد، مرتّبة بالأحدث. رد يدوياً أو دع الذكاء يرد.',
        how: 'اضغط «رسالة جديدة» لبدء محادثة مع رقم أو بريد غير موجود بعد.' },
      { href: '/templates', icon: FileText, title: 'القوالب', en: 'Templates',
        desc: 'رسائل جاهزة قابلة لإعادة الاستخدام لواتساب والبريد لتوحيد ردودك وتسريعها.',
        how: 'أنشئ قالباً واستدعِه أثناء الرد أو داخل الحملات.' },
      { href: '/sequences', icon: GitBranch, title: 'التسلسلات', en: 'Sequences',
        desc: 'سلاسل متابعة تلقائية متعددة الخطوات تعمل على مدى أيام دون تدخّل منك.',
        how: 'حدّد الخطوات والتوقيت والقناة لكل خطوة، وسيتوقف التسلسل عند أول رد.' },
      { href: '/campaigns', icon: Megaphone, title: 'الحملات', en: 'Campaigns',
        desc: 'استهدف شريحة من العملاء برسائل مجدولة، واربطها بتسلسل متابعة كامل.',
        how: 'اختر الجمهور والتسلسل والنسخ، ثم شغّل الحملة.' },
    ],
  },
  {
    title: 'الذكاء والأتمتة', en: 'AI & automation', icon: Sparkles, accent: 'text-purple-400',
    items: [
      { href: '/activity', icon: Sparkles, title: 'المساعد الذكي', en: 'AI Activity',
        desc: 'نظام مستقل يقيّم وضعك ويتصرّف نيابةً عنك ويسجّل كل قرار. أنت تتحكّم بمدى تحكّمه.',
        how: 'من هنا اختر الوضع: وكيل كامل / مساعد / يدوي / متوقّف — أو «شغّل الآن».' },
      { href: '/ab-tests', icon: FlaskConical, title: 'اختبارات A/B', en: 'A/B Tests',
        desc: 'اختبر نسختين من الرسالة، والنظام يرصد الأعلى في معدل الرد ويعتمدها قالباً تلقائياً.',
        how: 'أنشئ اختباراً بنسختين وراقب النتيجة تتحدّث آلياً.' },
      { href: '/analytics', icon: BarChart3, title: 'التحليلات', en: 'Analytics',
        desc: 'أداء التواصل بالأرقام: كم أُرسل، كم رد، وكم تحوّل — لتعرف ما ينجح.',
        how: 'راجع المؤشرات دورياً لتحسين حملاتك ورسائلك.' },
    ],
  },
  {
    title: 'الإعداد والإدارة', en: 'Setup & admin', icon: Settings, accent: 'text-gray-300',
    items: [
      { href: '/submissions', icon: CalendarCheck, title: 'الطلبات والحجوزات', en: 'Conversions',
        desc: 'المواعيد والطلبات التي التقطتها مسارات التحويل من عملائك.',
        how: 'تابع الحجوزات الواردة وحوّلها إلى صفقات.' },
      { href: '/team', icon: UserCog, title: 'الفريق', en: 'Team',
        desc: 'أضف أعضاء فريقك وحدّد صلاحية كل منهم على المساحة.',
        how: 'ادعُ عضواً بالبريد وعيّن دوره.' },
      { href: '/webhooks', icon: Webhook, title: 'الويب هوك', en: 'Webhooks',
        desc: 'استقبل أحداث النظام (رد جديد، صفقة مربوحة...) في أنظمتك الخارجية.',
        how: 'أضف رابط الاستقبال واختر الأحداث المطلوبة.' },
      { href: '/settings', icon: Settings, title: 'الإعدادات', en: 'Settings',
        desc: 'إعدادات المساحة واللغة والموافقة (قانون 151) وحدود التواصل.',
        how: 'اضبط تفضيلات حسابك ومستوى الموافقة التلقائية.' },
      { href: '/billing', icon: CreditCard, title: 'الفوترة', en: 'Billing',
        desc: 'خطتك واشتراكك وفواتيرك ومدة التجربة المجانية.',
        how: 'راجع خطتك وطرق الدفع وترقيتها.' },
    ],
  },
]

function StatPill({ label, value, icon: Icon, color }: { label: string; value: number | string; icon: Icon; color: string }) {
  return (
    <div className="flex items-center gap-3 bg-gray-900 border border-gray-800 rounded-xl p-3.5">
      <div className={clsx('w-9 h-9 rounded-lg flex items-center justify-center shrink-0', color)}>
        <Icon size={17} />
      </div>
      <div className="min-w-0">
        <div className="text-xl font-bold text-white leading-none">{value}</div>
        <div className="text-xs text-gray-400 font-cairo mt-1 truncate">{label}</div>
      </div>
    </div>
  )
}

function FeatureCard({ f }: { f: Feature }) {
  const Icon = f.icon
  return (
    <Link
      href={f.href}
      className="group relative bg-gray-900 border border-gray-800 hover:border-gold-primary/40 rounded-xl p-4 transition-all flex flex-col gap-2"
    >
      <div className="flex items-center gap-2.5">
        <div className="w-9 h-9 rounded-lg bg-gray-800 group-hover:bg-gold-primary/15 text-gray-300 group-hover:text-gold-primary flex items-center justify-center shrink-0 transition-colors">
          <Icon size={17} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            {f.step && (
              <span className="w-4 h-4 rounded-full bg-gold-primary text-gray-950 text-[10px] font-bold flex items-center justify-center shrink-0">{f.step}</span>
            )}
            <span className="text-sm font-semibold text-white font-cairo truncate">{f.title}</span>
          </div>
          <div className="text-[11px] text-gray-500">{f.en}</div>
        </div>
        <ArrowLeft size={15} className="text-gray-600 group-hover:text-gold-primary transition-colors shrink-0" />
      </div>
      <p className="text-xs text-gray-400 font-cairo leading-relaxed">{f.desc}</p>
      <p className="text-[11px] text-gold-primary/80 font-cairo leading-relaxed border-t border-gray-800 pt-2 mt-auto">
        <span className="font-semibold">كيف:</span> {f.how}
      </p>
    </Link>
  )
}

export default function DashboardPage() {
  const { data } = useSWR<DashboardStats>(
    '/dashboard/stats',
    () => dashboardApi.stats().then((r) => r.data),
    { refreshInterval: 60000 }
  )
  const stats = data ?? ({} as DashboardStats)

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white font-cairo">مرحباً بك في Qualifay</h1>
        <p className="text-gray-400 text-sm mt-1 font-cairo">
          دليلك لكل ميزات النظام — اضغط أي بطاقة للانتقال مباشرةً إلى الأداة.
        </p>
      </div>

      {/* Pulse */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatPill label="إجمالي العملاء" value={stats.total_leads ?? 0} icon={Users} color="bg-blue-500/10 text-blue-400" />
        <StatPill label="بانتظار المراجعة" value={stats.pending_review ?? 0} icon={CheckCircle} color="bg-gold-primary/10 text-gold-primary" />
        <StatPill label="رسائل واتساب اليوم" value={stats.wa_messages_today ?? 0} icon={MessageSquare} color="bg-wa-green/10 text-wa-green" />
        <StatPill label="حملات نشطة" value={stats.active_campaigns ?? 0} icon={Megaphone} color="bg-purple-500/10 text-purple-400" />
      </div>

      {/* Quick-start banner */}
      <div className="bg-gradient-to-l from-gold-primary/10 to-transparent border border-gold-primary/20 rounded-xl p-4">
        <div className="flex items-center gap-2 mb-1">
          <Rocket size={16} className="text-gold-primary" />
          <h2 className="text-sm font-bold text-white font-cairo">البدء السريع في 3 خطوات</h2>
        </div>
        <p className="text-xs text-gray-400 font-cairo leading-relaxed">
          اربط واتساب ← اربط بريدك ← اجمع أول دفعة عملاء. بعدها راجِع العملاء ووافق، ودع المساعد الذكي يتولّى الردود والمتابعات.
        </p>
      </div>

      {/* Feature groups */}
      {GROUPS.map((g) => {
        const GIcon = g.icon
        return (
          <section key={g.title}>
            <div className="flex items-center gap-2 mb-3">
              <GIcon size={17} className={g.accent} />
              <h2 className="text-base font-bold text-white font-cairo">{g.title}</h2>
              <span className="text-xs text-gray-600">{g.en}</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {g.items.map((f) => <FeatureCard key={f.href} f={f} />)}
            </div>
          </section>
        )
      })}

      <p className="text-center text-xs text-gray-600 font-cairo pt-2">
        تحتاج مساعدة في ميزة؟ افتحها واتبع سطر «كيف» في كل بطاقة.
      </p>
    </div>
  )
}
