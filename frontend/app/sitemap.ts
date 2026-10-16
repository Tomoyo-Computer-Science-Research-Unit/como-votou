import type { MetadataRoute } from "next";
import { CIDADES, SCREENS, cityRoute } from "@/lib/uf";

export const dynamic = "force-static";

const baseUrl = `https://g0v.tomoyo.systems${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}`;

export default function sitemap(): MetadataRoute.Sitemap {
  return CIDADES.flatMap((city) =>
    SCREENS.map((screen) => ({ url: `${baseUrl}${cityRoute(city, screen)}`, changeFrequency: "daily" as const, priority: city.kind === "capital" && screen === "/" ? 1 : 0.6 }))
  );
}
