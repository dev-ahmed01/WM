/** @type {import("next").NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  // Obsolete entry points now live inside the three-destination layout. Permanent so bookmarks keep working.
  async redirects() {
    return [
      { source: "/workspace", destination: "/copilot", permanent: true },
      { source: "/procedure-studio", destination: "/knowledge-studio", permanent: true },
      { source: "/copilot/sources", destination: "/knowledge-studio", permanent: true },
      { source: "/knowledge-gaps", destination: "/conversations", permanent: true },
      { source: "/handover/review", destination: "/escalation-centre", permanent: true },
      { source: "/work/exceptions", destination: "/escalation-centre?tab=blocked", permanent: true },
    ];
  },
};

export default nextConfig;
