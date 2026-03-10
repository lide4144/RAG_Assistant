/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const kernelBaseUrl =
      process.env.NEXT_PUBLIC_KERNEL_BASE_URL ??
      process.env.KERNEL_BASE_URL ??
      'http://127.0.0.1:8000';
    return [
      {
        source: '/api/admin/:path*',
        destination: `${kernelBaseUrl}/api/admin/:path*`
      },
      {
        source: '/api/library/:path*',
        destination: `${kernelBaseUrl}/api/library/:path*`
      },
      {
        source: '/api/tasks/:path*',
        destination: `${kernelBaseUrl}/api/tasks/:path*`
      }
    ];
  }
};

export default nextConfig;
