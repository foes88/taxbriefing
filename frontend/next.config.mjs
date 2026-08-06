/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 백엔드는 별도 호스트에 배포된다 (ADR-004). 로컬은 localhost:8000.
  env: {
    NEXT_PUBLIC_API_BASE:
      process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000/api/v1',
  },
};

export default nextConfig;
