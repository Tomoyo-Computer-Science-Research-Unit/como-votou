import type { Metadata } from "next";
import { cityConfig, CIDADES } from "@/lib/uf";

const SP = cityConfig(CIDADES.find((item) => item.key === "sp")!);

export const metadata: Metadata = { description: SP.description, keywords: SP.keywords, alternates: { canonical: "/sp/" } };

export default function SpLayout({ children }: { children: React.ReactNode }) {
  return children;
}
