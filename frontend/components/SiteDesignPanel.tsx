'use client'

// The owner's design decision for one business: collected data → reference style → logo colors → Build.
// Nothing is built until the owner clicks Build here.
import { useState } from 'react'
import useSWR from 'swr'
import toast from 'react-hot-toast'
import { Loader2, Wand2, Upload, Hammer, ExternalLink } from 'lucide-react'
import { siteFactoryApi } from '@/lib/api'

interface Reference { title: string; studio: string; url: string; fits: string }
interface Style {
  url?: string; title?: string; dark?: boolean; bg?: string; ink?: string; heading_font?: string; body_font?: string
  arabic_font?: string; uppercase?: boolean; radius?: number; thumbnail?: string
}
interface Palette { colors: string[]; primary: string | null; accent: string | null }
export interface DesignProspect {
  id: string; business_name: string; status: string
  profile: Record<string, unknown>
  design?: { style?: Style; colors?: { primary?: string; accent?: string | null }; has_logo?: boolean }
}

const HEX = /^#[0-9a-fA-F]{6}$/

function Fact({ k, v }: { k: string; v: unknown }) {
  if (v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length)) return null
  return (
    <div className="flex gap-2 text-xs">
      <span className="text-gray-500 w-24 flex-none">{k}</span>
      <span className="text-gray-200">{Array.isArray(v) ? (v as string[]).join(' · ') : String(v)}</span>
    </div>
  )
}

export default function SiteDesignPanel({ p, onBuilt }: { p: DesignProspect; onBuilt: () => void }) {
  const { data: refs } = useSWR('sf-references', () => siteFactoryApi.references().then((r) => r.data))
  const references: Reference[] = Array.isArray(refs) ? refs : []
  const [refUrl, setRefUrl] = useState(p.design?.style?.url || '')
  const [style, setStyle] = useState<Style | null>(p.design?.style || null)
  const [palette, setPalette] = useState<Palette | null>(null)
  const [primary, setPrimary] = useState(p.design?.colors?.primary || '')
  const [accent, setAccent] = useState(p.design?.colors?.accent || '')
  const [logoUrl, setLogoUrl] = useState('')
  const [busy, setBusy] = useState<'' | 'ref' | 'logo' | 'build'>('')
  const prof = p.profile || {}
  const links = (prof.links as Record<string, string>) || {}

  async function analyze() {
    if (!/^https?:\/\//.test(refUrl)) { toast.error('اختر موقعًا مرجعيًا أو الصق رابطًا يبدأ بـ https://'); return }
    setBusy('ref')
    try { setStyle((await siteFactoryApi.analyzeReference(refUrl)).data); toast.success('تم قراءة ستايل الموقع المرجعي') }
    catch { toast.error('تعذّر فتح الموقع المرجعي') } finally { setBusy('') }
  }

  async function uploadLogo(file?: File) {
    const fd = new FormData()
    if (file) fd.append('file', file)
    else if (logoUrl.startsWith('https://')) fd.append('url', logoUrl)
    else { toast.error('ارفع صورة اللوجو أو الصق رابطها (https://)'); return }
    setBusy('logo')
    try {
      const pal: Palette = (await siteFactoryApi.setLogo(p.id, fd)).data
      setPalette(pal)
      if (pal.primary) setPrimary(pal.primary)
      if (pal.accent) setAccent(pal.accent)
      toast.success('تم استخراج الألوان من اللوجو — راجعها قبل البناء')
    } catch { toast.error('تعذّر قراءة اللوجو') } finally { setBusy('') }
  }

  async function build() {
    if (!style) { toast.error('حلّل الموقع المرجعي أولًا'); return }
    if (!HEX.test(primary)) { toast.error('اختر اللون الأساسي'); return }
    setBusy('build')
    try {
      await siteFactoryApi.build(p.id, { style: { ...style, thumbnail: undefined }, colors: { primary, accent: HEX.test(accent) ? accent : null } })
      toast.success('بدأ بناء الموقع — يظهر في «بانتظار الموافقة» خلال دقيقة')
      onBuilt()
    } catch { toast.error('تعذّر بدء البناء') } finally { setBusy('') }
  }

  const input = 'w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-xs text-gray-100'
  return (
    <div className="grid lg:grid-cols-3 gap-5 font-cairo">
      {/* 1. what we collected */}
      <div className="space-y-2">
        <p className="text-gray-400 text-xs mb-1">١. البيانات التي جمعناها</p>
        <Fact k="الاسم" v={prof.name} />
        <Fact k="بالإنجليزية" v={prof.name_en} />
        <Fact k="النشاط" v={prof.category} />
        <Fact k="العنوان" v={prof.address} />
        <Fact k="الهاتف" v={prof.phone} />
        <Fact k="مواعيد العمل" v={prof.hours} />
        <Fact k="تقييم جوجل" v={prof.rating ? `${prof.rating} (${prof.reviews ?? 0})` : null} />
        {typeof prof.place_id === 'string' && (
          <a className="inline-flex items-center gap-1 text-xs text-gold-primary" target="_blank" rel="noopener"
            href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(String(prof.name || ''))}&query_place_id=${prof.place_id}`}>
            <ExternalLink size={12} /> على خرائط جوجل
          </a>
        )}
        {Object.entries(links).map(([k, u]) => (
          <a key={k} className="block text-xs text-gold-primary" href={u} target="_blank" rel="noopener">{k}</a>
        ))}
      </div>

      {/* 2. reference style */}
      <div className="space-y-2">
        <p className="text-gray-400 text-xs mb-1">٢. الموقع المرجعي (الستايل فقط — لا ننسخ محتواه)</p>
        <select className={input} value={references.some((r) => r.url === refUrl) ? refUrl : ''} onChange={(e) => setRefUrl(e.target.value)}>
          <option value="">— اختر من لوحة Awwwards —</option>
          {references.map((r) => <option key={r.url} value={r.url}>{r.title} · {r.fits}</option>)}
        </select>
        <input className={input} dir="ltr" placeholder="أو الصق رابط أي موقع https://…" value={refUrl} onChange={(e) => setRefUrl(e.target.value)} />
        <button onClick={analyze} disabled={!!busy} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-gray-800 text-gray-100 text-xs disabled:opacity-50">
          {busy === 'ref' ? <Loader2 size={13} className="animate-spin" /> : <Wand2 size={13} />} حلّل الستايل
        </button>
        {style && (
          <div className="rounded-lg border border-gray-800 p-2 space-y-1">
            {style.thumbnail && <img src={style.thumbnail} alt="" className="rounded w-full" />}
            <p className="text-xs text-gray-300">{style.dark ? 'داكن' : 'فاتح'} · {style.heading_font} / {style.arabic_font} · زوايا {style.radius}px{style.uppercase ? ' · عناوين كابيتال' : ''}</p>
          </div>
        )}
      </div>

      {/* 3. logo colors + build */}
      <div className="space-y-2">
        <p className="text-gray-400 text-xs mb-1">٣. ألوان من لوجو النشاط</p>
        <label className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-gray-800 text-gray-100 text-xs cursor-pointer">
          <Upload size={13} /> ارفع اللوجو
          <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => e.target.files?.[0] && uploadLogo(e.target.files[0])} />
        </label>
        <div className="flex gap-2">
          <input className={input} dir="ltr" placeholder="أو رابط اللوجو https://…" value={logoUrl} onChange={(e) => setLogoUrl(e.target.value)} />
          <button onClick={() => uploadLogo()} disabled={!!busy} className="px-3 rounded-lg bg-gray-800 text-xs text-gray-100 disabled:opacity-50">
            {busy === 'logo' ? <Loader2 size={13} className="animate-spin" /> : 'استخرج'}
          </button>
        </div>
        {palette && palette.colors.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {palette.colors.map((c) => (
              <button key={c} title={`${c} — اضغط: أساسي · Shift+اضغط: ثانوي`} onClick={(e) => (e.shiftKey ? setAccent(c) : setPrimary(c))}
                className="w-7 h-7 rounded border border-gray-700" style={{ background: c }} />
            ))}
          </div>
        )}
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs text-gray-400 space-y-1">الأساسي
            <span className="flex gap-1 items-center"><input type="color" value={HEX.test(primary) ? primary : '#1f4fd1'} onChange={(e) => setPrimary(e.target.value)} />
              <input className={input} dir="ltr" value={primary} onChange={(e) => setPrimary(e.target.value)} placeholder="#1f4fd1" /></span>
          </label>
          <label className="text-xs text-gray-400 space-y-1">الثانوي
            <span className="flex gap-1 items-center"><input type="color" value={HEX.test(accent) ? accent : '#f2a900'} onChange={(e) => setAccent(e.target.value)} />
              <input className={input} dir="ltr" value={accent} onChange={(e) => setAccent(e.target.value)} placeholder="#f2a900" /></span>
          </label>
        </div>
        <button onClick={build} disabled={!!busy || !style || !HEX.test(primary)}
          className="w-full inline-flex justify-center items-center gap-2 px-3 py-2 rounded-lg bg-gold-primary text-black font-semibold text-sm disabled:opacity-40">
          {busy === 'build' ? <Loader2 size={15} className="animate-spin" /> : <Hammer size={15} />} ابنِ الموقع بهذا التصميم
        </button>
        <p className="text-[11px] text-gray-500">يُبنى الموقع فقط بعد ضغطك هنا. بعد البناء يظهر في «بانتظار الموافقة» لتراجعه قبل أي تواصل.</p>
      </div>
    </div>
  )
}
