import type { MetadataRoute } from "next";
import { CITY } from "@/lib/uf";

export const dynamic = "force-static";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Vereadores",
    short_name: "Vereadores",
    description: `Votações nominais, presença e proposições na ${CITY.camara}.`,
    start_url: "/",
    display: "standalone",
    background_color: "#050505",
    theme_color: "#050505",
    icons: [{ src: "/icon.png", sizes: "512x512", type: "image/png" }]
  };
}
