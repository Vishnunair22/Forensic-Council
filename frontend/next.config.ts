import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: 'standalone',
  experimental: {
    optimizePackageImports: ['lucide-react', 'framer-motion', '@react-three/drei', '@react-three/fiber'],
  },
};

export default nextConfig;
