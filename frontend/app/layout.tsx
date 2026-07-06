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
      <head>
        {/* Apply the saved theme before paint to avoid a flash of the wrong theme. */}
        <script
          dangerouslySetInnerHTML={{
            __html: "try{if(localStorage.getItem('theme')==='light')document.documentElement.classList.add('light')}catch(e){}",
          }}
        />
      </head>
      <body className="bg-gray-950 text-gray-100 font-cairo antialiased min-h-screen">
        {children}
        <Toaster
          position="top-center"
          toastOptions={{
            style: {
              background: 'var(--toast-bg)',
              color: 'var(--toast-fg)',
              border: '1px solid var(--toast-border)',
              fontFamily: 'Cairo, sans-serif',
            },
            success: {
              iconTheme: { primary: '#C9A227', secondary: 'var(--toast-bg)' },
            },
            error: {
              iconTheme: { primary: '#ef4444', secondary: 'var(--toast-bg)' },
            },
          }}
        />
      </body>
    </html>
  )
}
