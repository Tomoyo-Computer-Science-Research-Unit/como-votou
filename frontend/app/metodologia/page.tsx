import type { Metadata } from "next";
import { Panel, Screen } from "@/components/ui";
import { formatInt, getMeta, getVereadores, getVotacoes } from "@/lib/static-api";

export const metadata: Metadata = { title: "Método" };

function flatten(prefix: string, value: unknown, out: Array<[string, string]>) {
  if (value === null || value === undefined) {
    return;
  }
  if (typeof value === "number" || typeof value === "string" || typeof value === "boolean") {
    out.push([prefix, typeof value === "number" ? formatInt(value) : String(value)]);
    return;
  }
  if (Array.isArray(value)) {
    out.push([prefix, `${value.length} itens`]);
    return;
  }
  if (typeof value === "object") {
    for (const [key, inner] of Object.entries(value as Record<string, unknown>)) {
      flatten(prefix ? `${prefix} · ${key}` : key, inner, out);
    }
  }
}

export default function MethodPage() {
  const meta = getMeta();
  const votacoes = getVotacoes();
  const vereadores = getVereadores();
  const semResultado = votacoes.filter((item) => !item.resultado).length;
  const coverage: Array<[string, string]> = [];
  for (const key of ["votacoes", "presenca", "proposicoes"]) {
    flatten(key, (meta.stats as Record<string, unknown>)[key], coverage);
  }
  const generated = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short", timeZone: "America/Sao_Paulo" }).format(new Date(meta.generated_at));

  return (
    <Screen columns="minmax(0, 1fr) 440px" rows="minmax(0, 1fr) minmax(0, 1fr)">
      <Panel title={<b>Método</b>} fill style={{ gridRow: "1 / span 2" }}>
        <div className="max-w-[72ch] space-y-5 text-[12.5px] leading-6 text-sumi">
          <section>
            <h3 className="serif text-[15px] text-ink">Fontes</h3>
            <p>
              A Câmara Municipal do Rio de Janeiro não publica API nem arquivos abertos da atividade legislativa. O que existe são páginas do site camara.rio e
              bases Lotus Domino em aplicnt.camara.rj.gov.br, consultadas por URL. Este site lê a lista de vereadores (atual e das legislaturas anteriores),
              a frequência mensal em plenário, as proposições do Sistema de Proposições Legislativas e as atas de sessão com discussões e votações. Última
              leitura: {generated}.
            </p>
          </section>
          <section>
            <h3 className="serif text-[15px] text-ink">Votações nominais</h3>
            <p>
              Não há painel de votação publicado como dado. O voto de cada vereador aparece só no texto da ata: “votaram SIM os Senhores Vereadores A, B, C …
              31 (trinta e um). E que votaram NÃO …”. O texto é lido por expressões regulares; a lista de nomes é conferida contra a contagem impressa na
              própria ata e só entra quando as duas batem. Abstenções são registradas quando a ata as nomeia. Ausências não constam da ata: são inferidas
              pela lista de quem estava em exercício no mês da sessão, descontando quem presidia a sessão quando a ata o nomeia. Das {formatInt(votacoes.length)} votações
              lidas, {formatInt(semResultado)} ficaram sem resultado detectado porque a redação foge dos padrões conhecidos.
            </p>
          </section>
          <section>
            <h3 className="serif text-[15px] text-ink">Presença</h3>
            <p>
              A frequência vem da tabela mensal publicada pela Câmara desde 2017: faltas, faltas abonadas e total por vereador, com as observações de licença.
              A Câmara revisa meses passados quando abona faltas; os meses recentes são relidos a cada rodada.
            </p>
          </section>
          <section>
            <h3 className="serif text-[15px] text-ink">Proposições e nomes</h3>
            <p>
              Projetos de lei, de lei complementar, de decreto legislativo, de resolução, emendas à Lei Orgânica e requerimentos de informação vêm das visões
              do SPL, com autor em texto livre. Nenhuma dessas fontes compartilha um identificador: a ligação entre ata, frequência, SPL e cadastro é feita por
              nome normalizado, com uma tabela de apelidos mantida no código. Os nomes que não casaram ficam listados na cobertura ao lado.
            </p>
          </section>
          <section>
            <h3 className="serif text-[15px] text-ink">O que não dá para dizer</h3>
            <p>
              Não há obstrução nem voto em separado nas atas, só sim, não e abstenção. A legislatura atual começa em 2025; a anterior entra onde a busca
              em texto das atas alcança. Votações simbólicas, que são a maioria, não têm voto individual e não aparecem.
            </p>
          </section>
          <section>
            <h3 className="serif text-[15px] text-ink">Código</h3>
            <p>ETL em Python e site estático em Next.js, no repositório da Tomoyo; cada download tem o checksum guardado.</p>
          </section>
        </div>
      </Panel>

      <Panel title={<b>Cobertura</b>} flush fill>
        <table className="ruled">
          <tbody>
            <tr>
              <td>Vereadores</td>
              <td className="num right">{formatInt(vereadores.length)}</td>
            </tr>
            <tr>
              <td>Votações nominais lidas</td>
              <td className="num right">{formatInt(votacoes.length)}</td>
            </tr>
            {coverage.map(([key, value]) => (
              <tr key={key}>
                <td className="max-w-[300px] truncate text-ash" title={key}>
                  {key}
                </td>
                <td className="num right">{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <Panel title={<b>Fontes lidas</b>} flush fill>
        <table className="ruled">
          <tbody>
            {meta.sources.map((source) => (
              <tr key={`${source.name}-${source.url}`}>
                <td className="max-w-[320px] truncate">
                  <a href={source.url} target="_blank" rel="noreferrer" className="text-ink underline decoration-fog underline-offset-4 hover:decoration-ink" title={source.url}>
                    {source.name}
                  </a>
                </td>
                <td className="num right faint">{source.count !== undefined ? formatInt(source.count) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </Screen>
  );
}
