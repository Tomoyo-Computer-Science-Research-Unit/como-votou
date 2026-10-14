import type { MetadataRoute } from "next";

export const dynamic = "force-static";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Como votou seu vereador",
    short_name: "Vereadores",
    description: "Votações nominais, presença e proposições na Câmara Municipal do Rio de Janeiro.",
    start_url: "/",
    display: "standalone",
    background_color: "#050505",
    theme_color: "#050505",
    icons: [{ src: "/mon.svg", sizes: "any", type: "image/svg+xml" }]
  };
}
