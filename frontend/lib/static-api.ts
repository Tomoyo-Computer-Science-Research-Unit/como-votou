/**
 * Camada de dados do site. O núcleo de cada cidade (`static-data.generated.json`) traz vereadores
 * com seus agregados, a lista de votações nominais com contagens e a cobertura; os votos de cada
 * votação e a lista de votos e proposições de cada vereador vêm em arquivos sob demanda. O
 * DataGate busca o núcleo da cidade da página e o instala com `setCore`; os getters leem o núcleo
 * instalado, de forma síncrona.
 */

import { cityConfig, dataUrl, type Cidade } from "@/lib/uf";

export type Voto = "sim" | "nao" | "abstencao" | "ausente" | "presidindo";
export type VotoTotais = Partial<Record<Voto, number>>;
export type PresencaMes = { faltas: number; abonadas: number; total: number };
export type PresencaAno = PresencaMes & { meses: number };
export type Vereador = {
  id: string;
  nome: string;
  nome_parlamentar: string | null;
  partido: string | null;
  partidos_por_legislatura: Record<string, string>;
  legislaturas: number[];
  situacao: string | null;
  foto: string | null;
  gabinete?: string | null;
  email?: string | null;
  perfil_url?: string | null;
  presenca: { por_ano: Record<string, PresencaAno>; por_mes: Record<string, PresencaMes> };
  votos: { por_legislatura: Record<string, VotoTotais>; por_ano: Record<string, VotoTotais>; total?: VotoTotais };
  participacao: number | null;
  com_maioria: number | null;
  contra_partido: number | null;
  proposicoes_por_tipo: Record<string, Record<string, number>>;
  totais?: Record<string, number>;
  /** Municípios do Estado do Rio: resultado do vereador nas eleições de 2020 e 2024 (TSE). */
  eleicoes?: Record<string, Eleicao>;
};
export type Eleicao = { partido: string; numero: string; votos: number; situacao: "eleito" | "suplente" | "nao_eleito" };
export type EleicaoMunicipio = { cadeiras: number; candidatos: number; votos_nominais: number };
export type MunicipioMeta = { slug: string; nome: string; ibge: number; nivel: number; sistema: string; url_camara: string | null; sapl_url: string | null };
export type Contagem = { sim: number; nao: number; abstencao: number; presentes_votando: number | null };
export type Votacao = {
  id: string;
  data: string;
  hora: string | null;
  sessao: { tipo: string | null; numero: string | null; fase: string | null } | null;
  proposicao: { id: string; tipo: string; numero: string; ano: number; ementa: string; autores: string[]; autores_ids?: string[] };
  /** O que foi a voto: veto, emenda, projeto, redacao_final, substitutivo. */
  objeto?: string | null;
  resultado: string | null;
  contagem: Contagem;
  lado_vencedor: Voto | null;
  por_partido: Record<string, VotoTotais>;
  fonte: string;
  /** Assunto como o painel o imprime (São Paulo); usado no título quando o voto não é sobre o texto de uma proposição. */
  titulo?: string;
};
export type Legislatura = { numero: number; inicio: string; fim: string };
export type Coverage = Record<string, unknown>;
export type Source = { name: string; url: string; accessed_at?: string; count?: number };
export type Core = {
  generated_at: string;
  municipio?: MunicipioMeta;
  eleicoes?: Record<string, EleicaoMunicipio>;
  tipo_labels?: Record<string, string>;
  legislaturas: Legislatura[];
  vereadores: Vereador[];
  votacoes: Votacao[];
  presenca_meses: string[];
  stats: Coverage;
  sources: Source[];
};
export type VotoLinha = { votacao_id: string; voto: Voto };
export type ProposicaoLinha = { id: string; tipo: string; numero: string; ano: number; ementa: string; data: string | null; coautores?: string[] };
export type VereadorDetalhe = { votos: VotoLinha[]; proposicoes: ProposicaoLinha[] };

let CURRENT: { city: Cidade; core: Core } | null = null;
const coreCache = new Map<string, Promise<Core>>();
const listeners = new Set<() => void>();

export function loadCore(city: Cidade): Promise<Core> {
  let pending = coreCache.get(city.key);
  if (!pending) {
    pending = fetch(dataUrl(city, "static-data.generated.json")).then((response) => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return response.json() as Promise<Core>;
    });
    pending.catch(() => coreCache.delete(city.key));
    coreCache.set(city.key, pending);
  }
  return pending;
}

export function setCore(city: Cidade, core: Core): void {
  if (CURRENT?.core === core) {
    return;
  }
  CURRENT = { city, core };
  queueMicrotask(() => listeners.forEach((listener) => listener()));
}

/** Avisa quando outro núcleo é instalado (barra de status, fora do DataGate). */
export function subscribeCore(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function currentCity(): Cidade | null {
  return CURRENT?.city ?? null;
}

function core(): Core {
  if (!CURRENT) {
    throw new Error("núcleo de dados não carregado");
  }
  return CURRENT.core;
}

export function getCore(): Core {
  return core();
}

export const VOTO_LABELS: Record<Voto, string> = { sim: "Sim", nao: "Não", abstencao: "Abstenção", ausente: "Ausente", presidindo: "Presidindo" };
/** Rótulos dos tipos de proposição: os da cidade e, nos municípios com SAPL, os da própria câmara. */
export function tipoLabel(tipo: string): string {
  if (!CURRENT) {
    return tipo;
  }
  return CURRENT.core.tipo_labels?.[tipo] ?? cityConfig(CURRENT.city).tipoLabels[tipo] ?? tipo;
}

/** "Veto ao PL-1861/2026", "Emenda ao PL-…", "PL-…": o que estava em votação, não só a proposição. */
export function votacaoTitle(votacao: Pick<Votacao, "objeto" | "proposicao" | "titulo">): string {
  const prefix: Record<string, string> = { veto: "Veto ao", emenda: "Emenda ao", redacao_final: "Redação final do", substitutivo: "Substitutivo ao" };
  const head = prefix[votacao.objeto ?? ""];
  const onText = head !== undefined || votacao.objeto === "projeto" || !votacao.objeto;
  if (votacao.titulo && (!votacao.proposicao.id || !onText)) {
    return votacao.titulo;
  }
  return head ? `${head} ${votacao.proposicao.id}` : votacao.proposicao.id;
}

/** "Em votação": o que a votação decidia. */
export const OBJETO_LABELS: Record<string, string> = {
  veto: "veto do prefeito",
  emenda: "emenda",
  redacao_final: "redação final",
  substitutivo: "substitutivo",
  requerimento: "requerimento",
  eleicao: "eleição da Mesa",
  contas: "parecer sobre contas",
  parecer: "parecer"
};
export function objetoLabel(objeto: string | null | undefined): string {
  return OBJETO_LABELS[objeto ?? ""] ?? "o projeto";
}

/** Resultado lido com o objeto: num veto, "não" derruba o veto e o projeto segue. */
export function resultadoLabel(votacao: Pick<Votacao, "objeto" | "resultado">): string {
  const key = `${votacao.objeto ?? ""}:${votacao.resultado ?? ""}`;
  const labels: Record<string, string> = {
    "veto:derrubado": "veto derrubado, projeto segue",
    "veto:mantido": "veto mantido",
    "veto:rejeitado": "veto derrubado, projeto segue",
    "veto:sem_quorum": "sem quórum",
    "emenda:aprovado": "emenda aprovada",
    "emenda:rejeitado": "emenda rejeitada",
    "emenda:prejudicado": "emenda prejudicada",
    "emenda:sem_quorum": "sem quórum",
    "projeto:aprovado": "aprovado",
    "projeto:rejeitado": "rejeitado",
    "projeto:prejudicado": "prejudicado",
    "projeto:sem_quorum": "sem quórum",
    "redacao_final:aprovado": "redação final aprovada",
    "substitutivo:aprovado": "substitutivo aprovado",
    "substitutivo:rejeitado": "substitutivo rejeitado",
    "projeto:pendente": "sem quórum, volta à pauta",
    "emenda:pendente": "sem quórum, volta à pauta",
    "substitutivo:pendente": "sem quórum, volta à pauta",
    "requerimento:pendente": "sem quórum",
    "requerimento:sem_quorum": "sem quórum",
    "eleicao:eleito": "eleito"
  };
  return labels[key] ?? (votacao.resultado ? votacao.resultado.replace(/_/g, " ") : "não detectado");
}

/** Lado favorável à proposição: num veto é o "não" (contra o veto). */
export function resultadoClass(votacao: Pick<Votacao, "objeto" | "resultado">): string {
  const good = (votacao.objeto === "veto" && (votacao.resultado === "derrubado" || votacao.resultado === "rejeitado")) || (votacao.objeto !== "veto" && votacao.resultado === "aprovado");
  const bad = (votacao.objeto === "veto" && votacao.resultado === "mantido") || (votacao.objeto !== "veto" && votacao.resultado === "rejeitado");
  return good ? "voto-sim" : bad ? "voto-nao" : "faint";
}

export function getMeta() {
  return { generated_at: core().generated_at, legislaturas: core().legislaturas, stats: core().stats, sources: core().sources, presenca_meses: core().presenca_meses ?? [] };
}
export function getLegislaturas(): Legislatura[] {
  return core().legislaturas;
}
export function getVereadores(): Vereador[] {
  return core().vereadores;
}
export function getVereador(id: string): Vereador | undefined {
  return core().vereadores.find((item) => item.id === id);
}
export function getVotacoes(): Votacao[] {
  return core().votacoes;
}
export function getVotacao(id: string): Votacao | undefined {
  return core().votacoes.find((item) => item.id === id);
}
export function getStats(): Coverage {
  return core().stats;
}
export function getSources(): Source[] {
  return core().sources;
}

/** Anos com presença apurada, do mais recente ao mais antigo. */
export function presencaYears(): number[] {
  const years = new Set<number>();
  for (const vereador of core().vereadores) {
    for (const key of Object.keys(vereador.presenca?.por_ano ?? {})) {
      years.add(Number(key));
    }
  }
  return [...years].sort((a, b) => b - a);
}

export function currentLegislatura(): Legislatura {
  return core().legislaturas[core().legislaturas.length - 1];
}

export function displayName(vereador: Pick<Vereador, "nome" | "nome_parlamentar">): string {
  return vereador.nome_parlamentar || vereador.nome;
}

export function sumVotos(totais: VotoTotais | undefined): number {
  return totais ? Object.values(totais).reduce((sum, value) => sum + (value ?? 0), 0) : 0;
}

export function formatPct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "–";
  }
  return `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value * 100)}%`;
}

export function formatInt(value: number | null | undefined): string {
  return value === null || value === undefined ? "–" : new Intl.NumberFormat("pt-BR").format(value);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "–";
  }
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

export function fileId(id: string): string {
  return id.replace(/[:/]/g, "-");
}

/** Mesma lógica do ETL: Vereador(a) Fulano -> Fulano em caixa normal. */
export function cleanAuthor(value: string): string {
  return value
    .replace(/^VEREADOR(A)?\s+/i, "")
    .toLowerCase()
    .replace(/(^|\s)(\S)/g, (match) => match.toUpperCase())
    .replace(/\b(De|Da|Do|Das|Dos|E)\b/g, (match) => match.toLowerCase());
}

// --- Arquivos sob demanda ------------------------------------------------------------------

async function fetchJson<T>(file: string): Promise<T> {
  if (!CURRENT) {
    throw new Error("núcleo de dados não carregado");
  }
  const response = await fetch(dataUrl(CURRENT.city, file));
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

// Os caches são por cidade: a chave leva a pasta de dados.
function cacheKey(id: string): string {
  return `${CURRENT?.city.key ?? ""}|${id}`;
}

const votosCache = new Map<string, Record<string, Voto>>();
const detalheCache = new Map<string, VereadorDetalhe>();

export type VotacaoDetalhe = Votacao & { votos: Record<string, Voto>; resultado_frase?: string | null; presidente?: string | null; roster_mes?: string | null };
const detalheVotacaoCache = new Map<string, VotacaoDetalhe | null>();

/** Arquivo da votação: votos por vereador e a ementa completa (o núcleo só leva um resumo). */
export async function loadVotacao(votacaoId: string): Promise<VotacaoDetalhe | null> {
  if (detalheVotacaoCache.has(cacheKey(votacaoId))) {
    return detalheVotacaoCache.get(cacheKey(votacaoId)) ?? null;
  }
  try {
    const detalhe = await fetchJson<VotacaoDetalhe>(`static-votacoes/${fileId(votacaoId)}.generated.json`);
    detalheVotacaoCache.set(cacheKey(votacaoId), detalhe);
    return detalhe;
  } catch {
    detalheVotacaoCache.set(cacheKey(votacaoId), null);
    return null;
  }
}

export async function loadVotos(votacaoId: string): Promise<Record<string, Voto>> {
  const cached = votosCache.get(cacheKey(votacaoId));
  if (cached) {
    return cached;
  }
  const detalhe = await loadVotacao(votacaoId);
  const votos = detalhe?.votos ?? {};
  votosCache.set(cacheKey(votacaoId), votos);
  return votos;
}

export async function loadVereador(id: string): Promise<VereadorDetalhe> {
  const cached = detalheCache.get(cacheKey(id));
  if (cached) {
    return cached;
  }
  try {
    const detalhe = await fetchJson<VereadorDetalhe>(`static-vereadores/${fileId(id)}.generated.json`);
    detalheCache.set(cacheKey(id), detalhe);
    return detalhe;
  } catch {
    const empty = { votos: [], proposicoes: [] };
    detalheCache.set(cacheKey(id), empty);
    return empty;
  }
}
