'use client'

export const dynamic = 'force-dynamic'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function RootPage() {
  const router = useRouter()
  useEffect(() => {
    const token = localStorage.getItem('qualifay_token')
    if (token) {
      router.replace('/leads')
    } else {
      router.replace('/login')
    }
  }, [router])
  return null
}
