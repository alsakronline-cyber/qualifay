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
    <html lang="ar" dir="rtl" className="dark light">
      <head>
        {/* Apply the saved theme before paint to avoid a flash of the wrong theme.
            The grey/white (light) palette is the default now, so only an explicit
            'dark' choice removes it — anyone who previously picked dark keeps it. */}
        <script
          dangerouslySetInnerHTML={{
            __html: "try{if(localStorage.getItem('theme')==='dark')document.documentElement.classList.remove('light')}catch(e){}",
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
              style: { borderLeft: '4px solid #25D366' },
              iconTheme: { primary: '#25D366', secondary: 'var(--toast-bg)' },
            },
            error: {
              style: { borderLeft: '4px solid #ef4444' },
              iconTheme: { primary: '#ef4444', secondary: 'var(--toast-bg)' },
            },
          }}
        />
      </body>
    </html>
  )
}
