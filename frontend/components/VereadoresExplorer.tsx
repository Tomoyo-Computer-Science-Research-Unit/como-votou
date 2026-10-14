"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { BarList } from "@/components/BarList";
import { useScreenHotkeys } from "@/components/Hotkeys";
import { MonthGrid } from "@/components/MonthGrid";
import { EmptyState, Panel, Screen, Segmented, Stat } from "@/components/ui";
import {
  TIPO_LABELS,
  VOTO_LABELS,
  currentLegislatura,
  displayName,
  formatDate,
  formatInt,
  formatPct,
  getVereadores,
  getVotacoes,
  loadVereador,
  sumVotos,
  type Vereador,
  type VereadorDetalhe,
  type Voto
} from "@/lib/static-api";

const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
type Sort = "faltas" | "participacao" | "proposicoes" | "nome";
type Scope = "exercicio" | "todos";
type View = "votos" | "proposicoes";
type VoteFilter = "todos" | "contra" | "ausencias";
const SORTS: Array<{ value: Sort; label: string }> = [
  { value: "faltas", label: "Faltas" },
  { value: "participacao", label: "Partic." },
  { value: "proposicoes", label: "Props." },
  { value: "nome", label: "Nome" }
];

function legYears(vereador: Vereador, start: number): string[] {
  return Object.keys(vereador.presenca?.por_ano ?? {}).filter((year) => Number(year) >= start);
}
function faltasLeg(vereador: Vereador, start: number): { total: number; abonadas: number; meses: number } {
  return legYears(vereador, start).reduce(
    (acc, year) => {
      const row = vereador.presenca.por_ano[year];
      return { total: acc.total + (row?.total ?? 0), abonadas: acc.abonadas + (row?.abonadas ?? 0), meses: acc.meses + (row?.meses ?? 0) };
    },
    { total: 0, abonadas: 0, meses: 0 }
  );
}
function proposicoesLeg(vereador: Vereador, start: number): Record<string, number> {
  const output: Record<string, number> = {};
  for (const [tipo, porAno] of Object.entries(vereador.proposicoes_por_tipo ?? {})) {
    for (const [year, count] of Object.entries(porAno)) {
      if (Number(year) >= start) {
        output[tipo] = (output[tipo] ?? 0) + count;
      }
    }
  }
  return output;
}

export function VereadoresExplorer() {
  const all = getVereadores();
  const leg = currentLegislatura();
  const legStart = Number(leg.inicio.slice(0, 4));
  const votacoes = useMemo(() => new Map(getVotacoes().map((item) => [item.id, item])), []);
  const [scope, setScope] = useState<Scope>("exercicio");
  const [sort, setSort] = useState<Sort>("faltas");
  const [view, setView] = useState<View>("votos");
  const [voteFilter, setVoteFilter] = useState<VoteFilter>("todos");
  const [selectedId, setSelectedId] = useState(all[0]?.id ?? "");
  const [detalhe, setDetalhe] = useState<VereadorDetalhe | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("v");
    if (id && all.some((item) => item.id === id)) {
      setSelectedId(id);
    }
    setHydrated(true);
  }, [all]);
  useEffect(() => {
    if (hydrated) {
      window.history.replaceState(null, "", `${window.location.pathname}?v=${encodeURIComponent(selectedId)}`);
    }
  }, [hydrated, selectedId]);

  const rows = useMemo(() => {
    const metric = (vereador: Vereador) =>
      sort === "faltas"
        ? faltasLeg(vereador, legStart).total
        : sort === "participacao"
          ? vereador.participacao ?? -1
          : sort === "proposicoes"
            ? Object.values(proposicoesLeg(vereador, legStart)).reduce((sum, value) => sum + value, 0)
            : 0;
    return all
      .filter((vereador) => scope === "todos" || vereador.situacao === "em_exercicio" || vereador.id === selectedId)
      .map((vereador) => ({ vereador, value: metric(vereador) }))
      .sort((a, b) => (sort === "nome" ? displayName(a.vereador).localeCompare(displayName(b.vereador), "pt-BR") : b.value - a.value));
  }, [all, legStart, scope, selectedId, sort]);
  const selected = all.find((item) => item.id === selectedId) ?? all[0];
  const index = Math.max(0, rows.findIndex((row) => row.vereador.id === selected?.id));

  useEffect(() => {
    let alive = true;
    setDetalhe(null);
    if (!selected) {
      return;
    }
    loadVereador(selected.id).then((data) => {
      if (alive) {
        setDetalhe(data);
      }
    });
    return () => {
      alive = false;
    };
  }, [selected]);

  const hotkeys = useMemo(
    () => ({
      ArrowUp: () => setSelectedId(rows[(index - 1 + rows.length) % rows.length]?.vereador.id ?? selectedId),
      ArrowDown: () => setSelectedId(rows[(index + 1) % rows.length]?.vereador.id ?? selectedId),
      ArrowLeft: () => setSort((current) => SORTS[(SORTS.findIndex((item) => item.value === current) - 1 + SORTS.length) % SORTS.length].value),
      ArrowRight: () => setSort((current) => SORTS[(SORTS.findIndex((item) => item.value === current) + 1) % SORTS.length].value),
      v: () => setView((current) => (current === "votos" ? "proposicoes" : "votos")),
      e: () => setScope((current) => (current === "exercicio" ? "todos" : "exercicio"))
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [index, rows, selectedId]
  );
  useScreenHotkeys(hotkeys);

  if (!selected) {
    return <EmptyState>SEM VEREADORES</EmptyState>;
  }

  const faltas = faltasLeg(selected, legStart);
  const props = proposicoesLeg(selected, legStart);
  const totalProps = Object.values(props).reduce((sum, value) => sum + value, 0);
  const votosLeg = selected.votos?.por_legislatura?.[String(leg.numero)] ?? selected.votos?.total ?? {};
  const votados = (votosLeg.sim ?? 0) + (votosLeg.nao ?? 0) + (votosLeg.abstencao ?? 0);
  const votoLinhas = (detalhe?.votos ?? [])
    .map((linha) => ({ linha, votacao: votacoes.get(linha.votacao_id) }))
    .filter(({ linha, votacao }) => {
      if (!votacao) {
        return false;
      }
      if (voteFilter === "contra") {
        return votacao.lado_vencedor && linha.voto !== votacao.lado_vencedor && (linha.voto === "sim" || linha.voto === "nao");
      }
      if (voteFilter === "ausencias") {
        return linha.voto === "ausente";
      }
      return true;
    });

  return (
    <Screen columns="320px minmax(0, 1fr) minmax(0, 1fr)" rows="auto minmax(0, 1fr) minmax(0, 1.3fr)">
      <Panel
        title={<b>{scope === "exercicio" ? "Em exercício" : "Todos"}</b>}
        aside={<Segmented label="Ordem" value={sort} options={SORTS} onChange={setSort} />}
        flush
        fill
        style={{ gridRow: "1 / span 3" }}
      >
        <ul className="menu" role="listbox" aria-label="Vereadores">
          {rows.map(({ vereador, value }) => (
            <li key={vereador.id} role="presentation">
              <button type="button" role="option" aria-selected={vereador.id === selected.id} onClick={() => setSelectedId(vereador.id)}>
                <span className="truncate">
                  {displayName(vereador)}
                  <span className="faint ml-1.5 text-[10px] tracking-[0.08em]">{vereador.partido}</span>
                </span>
                <span className="num">{sort === "participacao" ? formatPct(value < 0 ? null : value) : sort === "nome" ? "" : formatInt(value)}</span>
              </button>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel
        title={
          <span className="flex items-center gap-3">
            {selected.foto ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={`${BASE_PATH}/${selected.foto}`} alt="" className="photo photo--sm" loading="lazy" />
            ) : null}
            <span>
              <b className="serif text-[16px]">{displayName(selected)}</b>
              <span className="mt-0.5 block text-[10.5px] tracking-[0.12em] text-ash">
                {[
                  selected.partido,
                  selected.situacao === "em_exercicio" ? "em exercício" : selected.situacao?.replace(/_/g, " "),
                  selected.legislaturas.length ? `legislaturas ${selected.legislaturas.map((item) => `${item}ª`).join(", ")}` : null,
                  selected.gabinete,
                  selected.email
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </span>
          </span>
        }
        aside={
          selected.perfil_url ? (
            <a href={selected.perfil_url} target="_blank" rel="noreferrer" className="btn !h-7 !px-2 text-[10px]">
              Câmara
            </a>
          ) : null
        }
        style={{ gridColumn: "2 / span 2" }}
      >
        <div className="grid grid-cols-2 gap-x-8">
          <div>
            <Stat label={`Faltas na ${leg.numero}ª legislatura`} value={formatInt(faltas.total)} sub={faltas.abonadas ? `${formatInt(faltas.abonadas)} abonadas` : undefined} />
            <Stat label="Meses com presença apurada" value={formatInt(faltas.meses)} />
            <Stat label="Votações nominais em que votou" value={formatInt(votados)} sub={`de ${formatInt(sumVotos(votosLeg))}`} />
            <Stat label="Participação" value={formatPct(selected.participacao)} />
          </div>
          <div>
            <Stat label="Votou com a maioria" value={formatPct(selected.com_maioria)} />
            <Stat label="Votos contra a maioria do partido" value={formatInt(selected.contra_partido)} />
            <Stat label="Proposições na legislatura" value={formatInt(totalProps)} />
            <Stat label="Ausências em votações" value={formatInt(votosLeg.ausente ?? 0)} sub={votosLeg.presidindo ? `${formatInt(votosLeg.presidindo)} presidindo` : undefined} />
          </div>
        </div>
      </Panel>

      <Panel title={<b>Faltas por mês</b>}>
        <MonthGrid porMes={selected.presenca?.por_mes ?? {}} />
      </Panel>
      <Panel title={<b>Proposições por tipo</b>} flush fill>
        <BarList
          rows={Object.entries(props)
            .sort((a, b) => b[1] - a[1])
            .map(([tipo, count]) => ({ key: tipo, label: TIPO_LABELS[tipo] ?? tipo, value: count }))}
          empty="SEM PROPOSIÇÕES NA LEGISLATURA"
        />
      </Panel>

      <Panel
        title={<b>{view === "votos" ? "Votos" : "Proposições"}</b>}
        aside={
          <>
            {view === "votos" ? (
              <Segmented
                label="Filtro"
                value={voteFilter}
                options={[
                  { value: "todos", label: "Todos" },
                  { value: "contra", label: "Contra a maioria" },
                  { value: "ausencias", label: "Ausências" }
                ]}
                onChange={setVoteFilter}
              />
            ) : null}
            <Segmented
              label="Lista"
              value={view}
              options={[
                { value: "votos", label: "Votos" },
                { value: "proposicoes", label: "Proposições" }
              ]}
              onChange={setView}
            />
          </>
        }
        flush
        fill
        style={{ gridColumn: "2 / span 2" }}
      >
        {!detalhe ? (
          <EmptyState>CARREGANDO</EmptyState>
        ) : view === "votos" ? (
          votoLinhas.length === 0 ? (
            <EmptyState>SEM VOTOS NESTE FILTRO</EmptyState>
          ) : (
            <table className="ruled">
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Proposição</th>
                  <th>Ementa</th>
                  <th>Voto</th>
                  <th>Resultado</th>
                  <th className="right">Placar</th>
                </tr>
              </thead>
              <tbody>
                {votoLinhas.map(({ linha, votacao }) => {
                  const contra = votacao!.lado_vencedor && (linha.voto === "sim" || linha.voto === "nao") && linha.voto !== votacao!.lado_vencedor;
                  return (
                    <tr key={linha.votacao_id}>
                      <td className="num">{formatDate(votacao!.data)}</td>
                      <td>
                        <Link href={`/votacoes?v=${encodeURIComponent(votacao!.id)}`} className="text-ink hover:underline hover:underline-offset-4">
                          {votacao!.proposicao.id}
                        </Link>
                      </td>
                      <td className="max-w-[420px] truncate text-ash" title={votacao!.proposicao.ementa}>
                        {votacao!.proposicao.ementa.toLowerCase()}
                      </td>
                      <td className={`${linha.voto === "sim" ? "voto-sim" : linha.voto === "nao" ? "voto-nao" : "faint"} ${contra ? "font-medium" : ""}`}>{VOTO_LABELS[linha.voto as Voto] ?? linha.voto}</td>
                      <td className="faint">{votacao!.resultado ?? "–"}</td>
                      <td className="num right faint">
                        {votacao!.contagem.sim}–{votacao!.contagem.nao}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )
        ) : detalhe.proposicoes.length === 0 ? (
          <EmptyState>SEM PROPOSIÇÕES</EmptyState>
        ) : (
          <table className="ruled">
            <thead>
              <tr>
                <th>Data</th>
                <th>Proposição</th>
                <th>Ementa</th>
              </tr>
            </thead>
            <tbody>
              {detalhe.proposicoes.map((proposicao) => (
                <tr key={proposicao.id}>
                  <td className="num">{formatDate(proposicao.data)}</td>
                  <td className="whitespace-nowrap">{proposicao.id}</td>
                  <td className="max-w-[620px] truncate text-ash" title={proposicao.ementa}>
                    {proposicao.ementa.toLowerCase()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </Screen>
  );
}
