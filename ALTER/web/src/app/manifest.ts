import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "ALTER",
    short_name: "ALTER",
    description: "Personal AI control plane",
    start_url: "/",
    display: "standalone",
    background_color: "#08090c",
    theme_color: "#08090c",
    orientation: "portrait-primary",
    categories: ["productivity", "utilities"]
  };
}
