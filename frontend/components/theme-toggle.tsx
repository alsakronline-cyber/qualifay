'use client'

import { useEffect, useState, useCallback } from 'react'
import { Sun, Moon } from 'lucide-react'

/**
 * One-button dark/light toggle. Adds/removes the `.light` class on <html>, which flips
 * the CSS-variable palette (see globals.css) across the whole app. Persists to
 * localStorage; the no-flash script in app/layout.tsx applies it before paint.
 */
export default function ThemeToggle() {
  const [light, setLight] = useState(false)

  useEffect(() => {
    setLight(document.documentElement.classList.contains('light'))
  }, [])

  const toggle = useCallback(() => {
    const next = !document.documentElement.classList.contains('light')
    document.documentElement.classList.toggle('light', next)
    try { localStorage.setItem('theme', next ? 'light' : 'dark') } catch {}
    setLight(next)
  }, [])

  return (
    <button
      onClick={toggle}
      title={light ? 'الوضع الليلي' : 'الوضع النهاري'}
      aria-label="تبديل السمة"
      className="w-9 h-9 rounded-lg flex items-center justify-center text-gray-400 hover:text-gold-primary hover:bg-gray-800 transition-colors"
    >
      {light ? <Moon size={18} /> : <Sun size={18} />}
    </button>
  )
}
