// BIOS_BACKEND_URL lets a second instance (for example a benchmark backend) be targeted; default unchanged.
const BACKEND = process.env.BIOS_BACKEND_URL || "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Optional separate build directory, so a second build never overwrites a running dev server's .next.
  distDir: process.env.BIOS_NEXT_DIST_DIR || ".next",
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${BACKEND}/api/v1/:path*`,
      },
      {
        source: "/health",
        destination: `${BACKEND}/health`,
      },
    ];
  },
};

module.exports = nextConfig;

