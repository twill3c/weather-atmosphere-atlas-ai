/** @type {import('next').NextConfig} */
const nextConfig = {
  // 完全な静的書き出し。serverless function をひとつも作らない(SPEC N-01)
  output: 'export',
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
