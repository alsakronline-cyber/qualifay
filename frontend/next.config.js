/** @type {import('next').NextConfig} */
// basePath lets the SAME Dockerfile build either the production app (root path)
// or the dev/test app served under /dev (set NEXT_BASE_PATH=/dev at build time,
// e.g. from docker-compose.dev.yml), so both can share one nginx port (80/443)
// without needing a dedicated public port opened at the hosting provider level.
const basePath = process.env.NEXT_BASE_PATH || ''

const nextConfig = {
  output: 'standalone',
  basePath,
  assetPrefix: basePath || undefined,
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
