/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  typescript: { ignoreBuildErrors: true },
  eslint: { ignoreDuringBuilds: true },
  experimental: { serverComponentsExternalPackages: [] },
  async rewrites() {
    return [
      { source: '/api/:path*', destination: `${process.env.BACKEND_URL || 'http://127.0.0.1:5000'}/api/:path*` }
    ]
  }
}
module.exports = nextConfig
