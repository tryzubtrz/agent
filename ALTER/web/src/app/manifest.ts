import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "ALTER — Universal Digital Twin",
    short_name: "ALTER",
    description: "Owner-controlled AI control plane for tasks, browser sessions, memory, rules, models and connectors.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#050608",
    theme_color: "#050608",
    orientation: "portrait-primary",
    categories: ["productivity", "utilities"],
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any maskable"
      }
    ]
  };
}
