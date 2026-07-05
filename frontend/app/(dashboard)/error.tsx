'use client'

import { useEffect } from 'react'

export default function DashboardError({ error, reset }: { error: Error & { digest?: string }, reset: () => void }) {
  useEffect(() => {
    console.error('Dashboard error:', error)
  }, [error])

  return (
    <div style={{ padding: '40px', fontFamily: 'monospace', background: '#111', color: '#f00', minHeight: '100vh' }}>
      <h1>Dashboard Error (Debug)</h1>
      <p><strong>Message:</strong> {error.message}</p>
      <p><strong>Stack:</strong></p>
      <pre style={{ whiteSpace: 'pre-wrap', color: '#ff8', fontSize: '12px' }}>{error.stack}</pre>
      <button onClick={reset} style={{ marginTop: '20px', padding: '8px 16px' }}>Retry</button>
    </div>
  )
}
