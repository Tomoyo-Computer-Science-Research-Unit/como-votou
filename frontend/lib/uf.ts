/**
 * O que muda de uma cidade para outra: nomes, textos curtos e rótulos dos tipos de proposição.
 * As telas, os painéis e os componentes são os mesmos; cada build carrega os dados de uma cidade
 * (NEXT_PUBLIC_UF, "RJ" padrão) e só este módulo sabe qual é.
 */

import citiesFile from "@/data/cities.json";

/** Sigla da UF da cidade; uma capital por UF. */
export type Uf = string;
export type Cidade = { uf: Uf; slug: string; nome: string; root: boolean; href: string };

const LIST = (citiesFile as { cities: Array<{ uf: string; slug: string; nome: string; root?: boolean }> }).cities;
const ROOT_CITY = LIST.find((item) => item.root) ?? LIST[0];
const wanted = (process.env.NEXT_PUBLIC_UF ?? ROOT_CITY.uf).toUpperCase();
const CURRENT = LIST.find((item) => item.uf.toUpperCase() === wanted) ?? ROOT_CITY;

export const UF: Uf = CURRENT.uf.toUpperCase();

const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

/** Raiz comum das cidades: "/vereadores" em produção, "" nos testes. A cidade raiz mora nela; as demais em <raiz>/<slug>. */
export const SITE_ROOT = CURRENT.root ? BASE_PATH : BASE_PATH.replace(new RegExp(`/${CURRENT.slug}$`), "");

/** Cidades publicadas, na ordem de frontend/data/cities.json. */
export const CIDADES: Cidade[] = LIST.map((item) => ({
  uf: item.uf.toUpperCase(),
  slug: item.slug,
  nome: item.nome,
  root: Boolean(item.root),
  href: item.root ? `${SITE_ROOT}/` : `${SITE_ROOT}/${item.slug}/`
}));

/** Mesma tela noutra cidade (a seleção de vereador ou votação não se transfere). */
export function cityHref(cidade: Cidade, pathname: string): string {
  const rest = pathname.replace(/^\/+|\/+$/g, "");
  return rest ? `${cidade.href}${rest}/` : cidade.href;
}

/** A próxima cidade da lista (tecla u). */
export function nextCityHref(pathname: string): string {
  const index = CIDADES.findIndex((item) => item.uf === UF);
  return cityHref(CIDADES[(index + 1) % CIDADES.length], pathname);
}

type CityConfig = {
  cidade: string;
  camara: string;
  /** Rótulo curto da barra de status. */
  camaraCurta: string;
  description: string;
  keywords: string[];
  /** Botão que abre a fonte de uma votação. */
  fonteVotacao: string;
  tipoLabels: Record<string, string>;
};

const RJ: CityConfig = {
  cidade: "Rio de Janeiro",
  camara: "Câmara Municipal do Rio de Janeiro",
  camaraCurta: "Câmara do Rio",
  description:
    "Câmara Municipal do Rio de Janeiro: votações nominais, presença em plenário e proposições de cada vereador, extraídas das atas e dos sistemas públicos da Câmara.",
  keywords: ["Rio de Janeiro", "Câmara Municipal", "vereadores", "votações nominais", "presença", "dados públicos"],
  fonteVotacao: "Ata",
  tipoLabels: {
    PL: "Projeto de lei",
    PLC: "Projeto de lei complementar",
    PDL: "Projeto de decreto legislativo",
    PR: "Projeto de resolução",
    PELOM: "Emenda à Lei Orgânica",
    REQ: "Requerimento",
    REQINF: "Requerimento de informação",
    IND: "Indicação",
    MOC: "Moção",
    OFI: "Ofício",
    MSG: "Mensagem"
  }
};

const SP: CityConfig = {
  cidade: "São Paulo",
  camara: "Câmara Municipal de São Paulo",
  camaraCurta: "Câmara de São Paulo",
  description:
    "Câmara Municipal de São Paulo: votações nominais, presença em plenário e proposições de cada vereador, a partir dos dados abertos da Câmara (painel de votação, listas de presença por sessão e SPLegis).",
  keywords: ["São Paulo", "Câmara Municipal", "vereadores", "votações nominais", "presença", "dados abertos"],
  fonteVotacao: "Painel",
  tipoLabels: {
    PL: "Projeto de lei",
    PDL: "Projeto de decreto legislativo",
    PR: "Projeto de resolução",
    PLO: "Emenda à Lei Orgânica",
    IND: "Indicação",
    MOC: "Moção",
    RDP: "Requerimento D com processo",
    RPP: "Requerimento P com processo",
    DOCREC: "Documento recebido"
  }
};

/** Textos de cada cidade; uma cidade nova em cities.json precisa da sua entrada aqui. */
const TEXTS: Record<string, CityConfig> = { RJ, SP };

export const CITY: CityConfig = TEXTS[UF] ?? RJ;
