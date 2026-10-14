/** Texto da página Método, por cidade. Os números vêm dos dados do build. */
import { formatInt } from "@/lib/static-api";
import { UF } from "@/lib/uf";

export type MethodContext = { generated: string; votacoes: number; semResultado: number; stats: Record<string, unknown> };
export type MethodSection = { title: string; body: string };

function num(stats: Record<string, unknown>, path: string): number {
  let value: unknown = stats;
  for (const key of path.split(".")) {
    value = value && typeof value === "object" ? (value as Record<string, unknown>)[key] : undefined;
  }
  return typeof value === "number" ? value : 0;
}

function str(stats: Record<string, unknown>, path: string): string {
  let value: unknown = stats;
  for (const key of path.split(".")) {
    value = value && typeof value === "object" ? (value as Record<string, unknown>)[key] : undefined;
  }
  return typeof value === "string" ? value : "";
}

function mes(value: string): string {
  return value ? `${value.slice(5, 7)}/${value.slice(0, 4)}` : "–";
}

function rj(ctx: MethodContext): MethodSection[] {
  return [
    { title: "Fontes", body: `A Câmara Municipal do Rio de Janeiro não publica API nem arquivos abertos da atividade legislativa. O que existe são páginas do site camara.rio e bases Lotus Domino em aplicnt.camara.rj.gov.br, consultadas por URL. Este site lê a lista de vereadores (atual e das legislaturas anteriores), a frequência mensal em plenário, as proposições do Sistema de Proposições Legislativas e as atas de sessão com discussões e votações. Última leitura: ${ctx.generated}.` },
    { title: "Votações nominais", body: `Não há painel de votação publicado como dado. O voto de cada vereador aparece só no texto da ata: “votaram SIM os Senhores Vereadores A, B, C … 31 (trinta e um). E que votaram NÃO …”. O texto é lido por expressões regulares; a lista de nomes é conferida contra a contagem impressa na própria ata e só entra quando as duas batem. Abstenções são registradas quando a ata as nomeia. Ausências não constam da ata: são inferidas pela lista de quem estava em exercício no mês da sessão, descontando quem presidia a sessão quando a ata o nomeia. Das ${formatInt(ctx.votacoes)} votações lidas, ${formatInt(ctx.semResultado)} ficaram sem resultado detectado porque a redação foge dos padrões conhecidos.` },
    { title: "Presença", body: `A frequência vem da tabela mensal publicada pela Câmara desde 2017: faltas, faltas abonadas e total por vereador, com as observações de licença. A Câmara revisa meses passados quando abona faltas; os meses recentes são relidos a cada rodada.` },
    { title: "Proposições e nomes", body: `Projetos de lei, de lei complementar, de decreto legislativo, de resolução, emendas à Lei Orgânica e requerimentos de informação vêm das visões do SPL, com autor em texto livre. Nenhuma dessas fontes compartilha um identificador: a ligação entre ata, frequência, SPL e cadastro é feita por nome normalizado, com uma tabela de apelidos mantida no código. Os nomes que não casaram ficam listados na cobertura ao lado.` },
    { title: "O que não dá para dizer", body: `Não há obstrução nem voto em separado nas atas, só sim, não e abstenção. A legislatura atual começa em 2025; a anterior entra onde a busca em texto das atas alcança. Votações simbólicas, que são a maioria, não têm voto individual e não aparecem.` },
    { title: "Código", body: `ETL em Python e site estático em Next.js, no repositório da Tomoyo; cada download tem o checksum guardado.` }
  ];
}

function sp(ctx: MethodContext): MethodSection[] {
  const s = ctx.stats;
  return [
    {
      title: "Fontes",
      body: `A Câmara Municipal de São Paulo publica dados abertos da atividade legislativa. Este site lê o arquivo XML anual do painel de votações (VOTACOES_<ano>.xml), as listas de presença de cada sessão plenária em XML, o web service SPLegis (vereadores, mandatos, filiações, proposições e autores) e as páginas dos vereadores no portal da Câmara, de onde vêm o nome parlamentar e a foto. Todas as fontes trazem o código do vereador no SPLegis, e a ligação entre elas é feita por esse código. Última leitura: ${ctx.generated}.`
    },
    {
      title: "Votações nominais",
      body: `O painel registra, em cada votação nominal, o voto de cada vereador que votou e o partido dele naquele dia. Foram ${formatInt(ctx.votacoes)} votações nominais de 2021 até a última leitura; as ${formatInt(num(s, "votacoes.simbolicas_fora"))} votações simbólicas do mesmo período não têm voto individual e ficam de fora. Entram as votações de projetos, emendas, substitutivos e vetos e também as de requerimentos (adiamento, suspensão ou prorrogação da sessão, inversão de pauta, criação de CPI), de pareceres sobre contas e as eleições da Mesa. Em ${formatInt(num(s, "votacoes.impresso_discrepancies"))} casos a contagem impressa pelo painel difere da lista de nomes, quase sempre por um voto; a contagem do site é a da lista. “Pendente de votação” é o registro do painel quando a votação nominal não alcança o quórum e a matéria volta à pauta; ${formatInt(ctx.semResultado)} votações ficaram sem resultado reconhecido.`
    },
    {
      title: "Ausência nas votações",
      body: `Ausente numa votação é o vereador em exercício no dia da sessão que não tem voto no painel. Em exercício quer dizer que consta da lista de presença daquela sessão com qualquer marca diferente do asterisco que a Câmara usa para suplente fora do mandato ou vereador que renunciou. No Rio a mesma conta usa a lista do mês; em São Paulo usa a da sessão. Das ${formatInt(num(s, "votacoes.ausencias"))} ausências contadas, ${formatInt(num(s, "votacoes.ausencias_presentes_na_sessao"))} são de vereadores que marcaram presença na sessão e não votaram, entre eles quem presidia os trabalhos, que em regra não vota. O painel não diz quem presidia, então ninguém aparece como presidindo.`
    },
    {
      title: "Presença",
      body: `A Câmara publica a lista de presença de cada sessão plenária, ordinária ou extraordinária: presente, licença (com o motivo do Regimento), falta justificada ou marca em branco. Faltas do mês são as sessões com a marca em branco; faltas abonadas são licenças e justificativas (nenhuma sessão do período traz a marca de falta justificada; todas as abonadas são licenças); o total soma as duas. Foram lidas ${formatInt(num(s, "presenca.sessoes"))} sessões, de ${mes(str(s, "presenca.primeiro_mes"))} a ${mes(str(s, "presenca.ultimo_mes"))}. Sessões dos últimos 45 dias são relidas a cada rodada, porque justificativas são registradas depois.`
    },
    {
      title: "Proposições",
      body: `Projetos de lei, de decreto legislativo, de resolução e de emenda à Lei Orgânica, indicações, moções e os requerimentos com processo (CPIs, convocação de secretários) vêm do SPLegis, com o código de cada autor, a partir de 2021. Os requerimentos sem processo, perto de dois mil por ano (pedidos de coautoria, votos de júbilo, licenças, inclusão em pauta), ficam de fora.`
    },
    {
      title: "O que não dá para dizer",
      body: `A legislatura atual (19ª) começa em 2025; a anterior (18ª, 2021–2024) entra inteira. O partido numa votação é o que o painel imprimiu naquele dia; na lista de vereadores vale o último partido registrado na legislatura. O painel tem uma coluna de votos em branco; ela está zerada em todas as votações do período.`
    },
    { title: "Código", body: "ETL em Python e site estático em Next.js, no repositório da Tomoyo; cada download tem o checksum guardado." }
  ];
}

export function methodSections(ctx: MethodContext): MethodSection[] {
  const builders: Record<string, (ctx: MethodContext) => MethodSection[]> = { RJ: rj, SP: sp };
  return (builders[UF] ?? rj)(ctx);
}
