/**
 * As cidades do site e o que muda entre elas: nomes, textos curtos, rótulos dos tipos de proposição.
 * Um só build serve todas: Rio (capital) na raiz, São Paulo em /sp/, os municípios do Estado do Rio
 * em /rj/<slug>/. A cidade de uma página sai do endereço (cityFromPath); os dados de cada uma vêm por
 * fetch de public/data/<dir>/ (scripts/stage-data.mjs).
 */

import citiesFile from "@/data/cities.json";
import municipiosFile from "@/data/rj-municipios.json";

export type Cidade = {
  /** "rj", "sp" ou "rj/<slug>". */
  key: string;
  /** Pasta dos dados em public/data/. */
  dir: string;
  slug: string;
  nome: string;
  /** Prefixo das rotas da cidade: "" (Rio), "/sp", "/rj/<slug>". */
  prefix: string;
  kind: "capital" | "municipio";
  /** Nível de dado: 0 só vereadores (TSE), 1 proposições, 2 presença, 3 votos nominais. */
  nivel: number;
  sistema: string | null;
  urlCamara: string | null;
};

export type MunicipioIndex = {
  slug: string;
  nome: string;
  ibge: number;
  nivel: number;
  sistema: string;
  url_camara: string | null;
  cadeiras?: number;
  votacoes?: number;
  presencas?: number;
  proposicoes?: number;
  ultima_votacao?: string | null;
  capital?: boolean;
};

export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

const CAPITAIS = (citiesFile as { cities: Array<{ uf: string; slug: string; nome: string; root?: boolean }> }).cities;
export const MUNICIPIOS = (municipiosFile as { municipios: MunicipioIndex[] }).municipios;
const RIO_INDEX = MUNICIPIOS.find((item) => item.capital);

const capitais: Cidade[] = CAPITAIS.map((item) => ({
  key: item.slug,
  dir: item.slug,
  slug: item.slug,
  nome: item.nome,
  prefix: item.root ? "" : `/${item.slug}`,
  kind: "capital",
  nivel: 3,
  sistema: item.root ? RIO_INDEX?.sistema ?? null : null,
  urlCamara: item.root ? RIO_INDEX?.url_camara ?? null : null
}));

const municipios: Cidade[] = MUNICIPIOS.filter((item) => !item.capital)
  .map((item) => ({
    key: `rj/${item.slug}`,
    dir: `rjm/${item.slug}`,
    slug: item.slug,
    nome: item.nome,
    prefix: `/rj/${item.slug}`,
    kind: "municipio" as const,
    nivel: item.nivel,
    sistema: item.sistema,
    urlCamara: item.url_camara
  }))
  .sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));

/** Capitais primeiro (Rio, São Paulo), depois os municípios do Estado do Rio em ordem alfabética. */
export const CIDADES: Cidade[] = [...capitais, ...municipios];
export const ROOT_CITY: Cidade = capitais.find((item) => item.prefix === "") ?? capitais[0];

/** Telas, na ordem das teclas 1–5. */
export const SCREENS = ["/", "/votacoes", "/presenca", "/partidos", "/metodologia"] as const;

/** Cidade e tela de um caminho sem basePath ("/rj/niteroi/votacoes/" -> Niterói, "/votacoes"). */
export function splitPath(pathname: string): { city: Cidade; screen: string } {
  const clean = `/${pathname.replace(/^\/+|\/+$/g, "")}`;
  const parts = clean.split("/").filter(Boolean);
  let city = ROOT_CITY;
  let rest = parts;
  if (parts[0] === "rj" && parts[1]) {
    city = municipios.find((item) => item.slug === parts[1]) ?? ROOT_CITY;
    rest = parts.slice(2);
  } else if (parts[0]) {
    const capital = capitais.find((item) => item.prefix === `/${parts[0]}`);
    if (capital) {
      city = capital;
      rest = parts.slice(1);
    }
  }
  return { city, screen: rest.length ? `/${rest.join("/")}` : "/" };
}

export function cityFromPath(pathname: string): Cidade {
  return splitPath(pathname).city;
}

/** Rota da tela na cidade, sem basePath (para Link e router). */
export function cityRoute(cidade: Cidade, screen: string): string {
  return screen === "/" ? `${cidade.prefix}/` : `${cidade.prefix}${screen}/`;
}

/** Endereço completo, com basePath (para window.location). */
export function cityHref(cidade: Cidade, screen: string): string {
  return `${BASE_PATH}${cityRoute(cidade, screen)}`;
}

/** A próxima cidade da lista, na mesma tela (tecla u). */
export function nextCityHref(pathname: string): string {
  const { city, screen } = splitPath(pathname);
  const index = CIDADES.findIndex((item) => item.key === city.key);
  return cityHref(CIDADES[(index + 1) % CIDADES.length], screen);
}

/** URL de um arquivo de dados da cidade. */
export function dataUrl(cidade: Cidade, file: string): string {
  return `${BASE_PATH}/data/${cidade.dir}/${file}`;
}

export type CityConfig = {
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

export function deCidade(nome: string): string {
  return `de ${nome}`;
}

function municipioConfig(cidade: Cidade): CityConfig {
  const camara = `Câmara Municipal ${deCidade(cidade.nome)}`;
  return {
    cidade: cidade.nome,
    camara,
    camaraCurta: `Câmara ${deCidade(cidade.nome)}`,
    description:
      cidade.nivel >= 3
        ? `${camara} (RJ): vereadores eleitos em 2020 e 2024, votações nominais, presença em plenário e proposições de cada vereador, a partir do TSE e do sistema da Câmara.`
        : `${camara} (RJ): vereadores eleitos em 2020 e 2024, com partido e votos, a partir dos dados abertos do TSE, e o que a Câmara publica da atividade de cada um.`,
    keywords: [cidade.nome, "Câmara Municipal", "vereadores", "eleições 2024", "Estado do Rio de Janeiro"],
    fonteVotacao: "SAPL",
    tipoLabels: RJ.tipoLabels
  };
}

const TEXTS: Record<string, CityConfig> = { rj: RJ, sp: SP };

export function cityConfig(cidade: Cidade): CityConfig {
  return cidade.kind === "capital" ? TEXTS[cidade.key] ?? RJ : municipioConfig(cidade);
}

export const ROOT_CONFIG = RJ;
