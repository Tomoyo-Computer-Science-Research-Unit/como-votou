import type { Metadata } from "next";
import { CIDADES, cityConfig } from "@/lib/uf";

// Os municípios do Estado do Rio (menos a capital, que mora na raiz) em /rj/<slug>/, com as mesmas telas.
export const dynamicParams = false;

const MUNICIPIOS = CIDADES.filter((item) => item.kind === "municipio");

export function generateStaticParams() {
  return MUNICIPIOS.map((item) => ({ municipio: item.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ municipio: string }> }): Promise<Metadata> {
  const { municipio } = await params;
  const city = MUNICIPIOS.find((item) => item.slug === municipio);
  if (!city) {
    return {};
  }
  const config = cityConfig(city);
  return {
    title: { default: `${city.nome} · Vereadores`, template: `%s · ${city.nome} · Vereadores` },
    description: config.description,
    keywords: config.keywords,
    alternates: { canonical: `/rj/${city.slug}/` }
  };
}

export default function MunicipioLayout({ children }: { children: React.ReactNode }) {
  return children;
}
