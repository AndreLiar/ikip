import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // The app is a BFF: browser talks only to same-origin /api route handlers, which
  // proxy to the FastAPI service (IKIP_API_URL) with a server-side token. No secrets
  // or tokens ever reach the browser (Story 4.4 AC4 — access control applied).
  reactStrictMode: true,
};

export default nextConfig;
