import type { Metadata } from 'next'
import { Toaster } from 'react-hot-toast'
import './globals.css'

export const metadata: Metadata = {
  title: 'Qualifay — نظام إدارة العملاء المحتملين',
  description: 'AI-powered lead qualification and WhatsApp CRM platform',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ar" dir="rtl" className="dark">
      <body className="bg-gray-950 text-gray-100 font-cairo antialiased min-h-screen">
        {children}
        <Toaster
          position="top-center"
          toastOptions={{
            style: {
              background: '#1f2937',
              color: '#f9fafb',
              border: '1px solid #374151',
              fontFamily: 'Cairo, sans-serif',
            },
            success: {
              iconTheme: { primary: '#C9A227', secondary: '#1f2937' },
            },
            error: {
              iconTheme: { primary: '#ef4444', secondary: '#1f2937' },
            },
          }}
        />
      </body>
    </html>
  )
}
