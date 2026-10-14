'use client'

import { useEffect } from 'react'
import { AlertTriangle, RotateCw } from 'lucide-react'

export default function DashboardError({ error, reset }: { error: Error & { digest?: string }, reset: () => void }) {
  useEffect(() => {
    console.error('Dashboard error:', error)
  }, [error])

  return (
    <div className="max-w-lg mx-auto py-12 sm:py-20">
      <div className="card p-6 sm:p-8 text-center">
        <div className="mx-auto mb-4 w-12 h-12 rounded-2xl bg-red-500/10 flex items-center justify-center">
          <AlertTriangle size={22} className="text-red-400" />
        </div>
        <h1 className="text-lg font-bold text-white font-cairo">حدث خطأ أثناء عرض هذه الصفحة</h1>
        <p className="text-sm text-gray-400 font-cairo mt-1.5">
          حاول مرة أخرى. إن تكرر الخطأ، أرسل التفاصيل أدناه للدعم.
        </p>
        <button
          onClick={reset}
          className="mt-6 inline-flex items-center gap-2 bg-gold-primary text-gray-950 font-semibold font-cairo text-sm px-5 py-2.5 rounded-xl hover:brightness-110 transition"
        >
          <RotateCw size={15} /> إعادة المحاولة
        </button>
        {/* Kept for support/debugging, but folded away instead of shown to every user. */}
        <details className="mt-6 text-start">
          <summary className="cursor-pointer text-xs text-gray-500 font-cairo">التفاصيل التقنية</summary>
          <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-gray-800/60 p-3 text-[11px] leading-relaxed text-gray-400 whitespace-pre-wrap break-all" dir="ltr">
            {error.message}
            {error.digest ? `\ndigest: ${error.digest}` : ''}
            {error.stack ? `\n\n${error.stack}` : ''}
          </pre>
        </details>
      </div>
    </div>
  )
}
