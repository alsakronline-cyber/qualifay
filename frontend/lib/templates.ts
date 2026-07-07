// Shared template rendering — {{name}} {{company}} {{industry}} {{city}} → lead data.
export const TEMPLATE_VARS = [
  { key: '{{name}}', label: 'الاسم' },
  { key: '{{company}}', label: 'الشركة' },
  { key: '{{industry}}', label: 'المجال' },
  { key: '{{city}}', label: 'المدينة' },
]

export const TEMPLATE_SAMPLE: Record<string, string> = {
  name: 'أحمد', company: 'شركة النور', industry: 'المقاولات', city: 'القاهرة',
}

export function renderTemplate(text: string, data: Record<string, string> = TEMPLATE_SAMPLE): string {
  return (text || '').replace(/\{\{(\w+)\}\}/g, (_, k) => data[k] ?? '')
}
