import type { NextConfig } from "next";

// STATIC_EXPORT=1 builds plain files into out/ for Firebase Hosting (the page talks to the API from the browser).
const nextConfig: NextConfig = process.env.STATIC_EXPORT ? { output: "export", distDir: ".next-export", images: { unoptimized: true } } : {};

export default nextConfig;
