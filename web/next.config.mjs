/** @type {import('next').NextConfig} */
const nextConfig = {
  // The Python media worker base URL (transcribe / render / serve-video).
  env: {
    NEXT_PUBLIC_WORKER_URL: process.env.NEXT_PUBLIC_WORKER_URL || "http://localhost:8000",
  },
};

export default nextConfig;
