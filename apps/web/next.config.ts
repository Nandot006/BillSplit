import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // packages/shared-types is plain TypeScript source (no build step), shared
  // with the mobile app. Compile it as part of this app.
  transpilePackages: ["@billsplit/shared-types"],
};

export default nextConfig;
