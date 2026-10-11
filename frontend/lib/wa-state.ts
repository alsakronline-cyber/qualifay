// A WhatsApp number's state as the client should understand it. Computed by the backend
// (/dashboard/home → numbers) from live connection + age + pause; mirrors the drip rules:
// days 0-13 replies only, days 14-20 a reduced limit, day 21+ the normal limit.

export type NumberState = 'active' | 'warming' | 'quiet' | 'paused' | 'disconnected'

export interface NumberRow {
  id: string
  name: string
  phone?: string | null
  state: NumberState
  day: number
  quiet_days_left: number
  sent_today: number
  daily_limit: number
}

export const QUIET_DAYS = 14
export const FULL_DAYS = 21

export const NUMBER_STATE: Record<NumberState, { label: string; tone: string; hint: (n: NumberRow) => string }> = {
  active: { label: 'نشط', tone: 'text-green-400 bg-green-500/10 border-green-500/30',
    hint: (n) => `أرسل ${n.sent_today} من ${n.daily_limit} رسالة حملات اليوم` },
  warming: { label: 'يزيد تدريجياً', tone: 'text-sky-400 bg-sky-500/10 border-sky-500/30',
    hint: (n) => `حد يومي مخفّض (${n.daily_limit}) لحماية الرقم — يصل للحد الكامل بعد ${Math.max(FULL_DAYS - n.day, 0)} يوم` },
  quiet: { label: 'فترة الحماية', tone: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
    hint: (n) => `رقم جديد: يرد على الرسائل فقط — تبدأ الحملات بعد ${n.quiet_days_left} يوم` },
  paused: { label: 'متوقف مؤقتاً', tone: 'text-gray-300 bg-gray-500/10 border-gray-500/30',
    hint: () => 'لا يرسل حملات — الردود في صندوق الوارد تعمل' },
  disconnected: { label: 'غير متصل', tone: 'text-red-400 bg-red-500/10 border-red-500/30',
    hint: () => 'أعد ربط الرقم لاستئناف الإرسال والردود' },
}
