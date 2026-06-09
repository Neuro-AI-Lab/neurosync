import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@neuro-sync/contracts"],
  experimental: {
    typedRoutes: true,
  },
};

export default nextConfig;
