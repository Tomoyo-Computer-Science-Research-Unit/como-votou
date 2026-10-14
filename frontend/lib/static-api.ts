/**
 * Camada de dados do site. O núcleo (`static-data.generated.json`) traz vereadores com seus
 * agregados, a lista de votações nominais com contagens e a cobertura; os votos de cada votação
 * e a lista de votos e proposições de cada vereador vêm em arquivos sob demanda.
 */

import snapshot from "@/lib/static-data.generated.json";

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
};
export type Contagem = { sim: number; nao: number; abstencao: number; presentes_votando: number | null };
export type Votacao = {
  id: string;
  data: string;
  hora: string | null;
  sessao: { tipo: string | null; numero: string | null; fase: string | null } | null;
  proposicao: { id: string; tipo: string; numero: string; ano: number; ementa: string; autores: string[]; autores_ids?: string[] };
  resultado: string | null;
  contagem: Contagem;
  lado_vencedor: Voto | null;
  por_partido: Record<string, VotoTotais>;
  fonte: string;
};
export type Legislatura = { numero: number; inicio: string; fim: string };
export type Coverage = Record<string, unknown>;
export type Source = { name: string; url: string; accessed_at?: string; count?: number };
type Core = {
  generated_at: string;
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

const DATA = snapshot as unknown as Core;

export const VOTO_LABELS: Record<Voto, string> = { sim: "Sim", nao: "Não", abstencao: "Abstenção", ausente: "Ausente", presidindo: "Presidindo" };
export const TIPO_LABELS: Record<string, string> = {
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
};

export function getMeta() {
  return { generated_at: DATA.generated_at, legislaturas: DATA.legislaturas, stats: DATA.stats, sources: DATA.sources, presenca_meses: DATA.presenca_meses ?? [] };
}
export function getLegislaturas(): Legislatura[] {
  return DATA.legislaturas;
}
export function getVereadores(): Vereador[] {
  return DATA.vereadores;
}
export function getVereador(id: string): Vereador | undefined {
  return DATA.vereadores.find((item) => item.id === id);
}
export function getVotacoes(): Votacao[] {
  return DATA.votacoes;
}
export function getVotacao(id: string): Votacao | undefined {
  return DATA.votacoes.find((item) => item.id === id);
}
export function getStats(): Coverage {
  return DATA.stats;
}
export function getSources(): Source[] {
  return DATA.sources;
}

/** Anos com presença apurada, do mais recente ao mais antigo. */
export function presencaYears(): number[] {
  const years = new Set<number>();
  for (const vereador of DATA.vereadores) {
    for (const key of Object.keys(vereador.presenca?.por_ano ?? {})) {
      years.add(Number(key));
    }
  }
  return [...years].sort((a, b) => b - a);
}

export function currentLegislatura(): Legislatura {
  return DATA.legislaturas[DATA.legislaturas.length - 1];
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

const votosCache = new Map<string, Record<string, Voto>>();
const detalheCache = new Map<string, VereadorDetalhe>();

export type VotacaoDetalhe = Votacao & { votos: Record<string, Voto>; resultado_frase?: string | null; presidente?: string | null; roster_mes?: string | null };
const detalheVotacaoCache = new Map<string, VotacaoDetalhe | null>();

/** Arquivo da votação: votos por vereador e a ementa completa (o núcleo só leva um resumo). */
export async function loadVotacao(votacaoId: string): Promise<VotacaoDetalhe | null> {
  if (detalheVotacaoCache.has(votacaoId)) {
    return detalheVotacaoCache.get(votacaoId) ?? null;
  }
  try {
    const module = (await import(`@/lib/static-votacoes/${fileId(votacaoId)}.generated.json`)) as { default?: VotacaoDetalhe };
    const detalhe = (module.default ?? module) as VotacaoDetalhe;
    detalheVotacaoCache.set(votacaoId, detalhe);
    return detalhe;
  } catch {
    detalheVotacaoCache.set(votacaoId, null);
    return null;
  }
}

export async function loadVotos(votacaoId: string): Promise<Record<string, Voto>> {
  const cached = votosCache.get(votacaoId);
  if (cached) {
    return cached;
  }
  const detalhe = await loadVotacao(votacaoId);
  const votos = detalhe?.votos ?? {};
  votosCache.set(votacaoId, votos);
  return votos;
}

export async function loadVereador(id: string): Promise<VereadorDetalhe> {
  const cached = detalheCache.get(id);
  if (cached) {
    return cached;
  }
  try {
    const module = (await import(`@/lib/static-vereadores/${fileId(id)}.generated.json`)) as { default?: VereadorDetalhe };
    const detalhe = (module.default ?? module) as VereadorDetalhe;
    detalheCache.set(id, detalhe);
    return detalhe;
  } catch {
    const empty = { votos: [], proposicoes: [] };
    detalheCache.set(id, empty);
    return empty;
  }
}
