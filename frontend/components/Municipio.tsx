"use client";

import { useEffect, useMemo, useState } from "react";
import { BarList } from "@/components/BarList";
import { sistemaLabel } from "@/components/CoberturaRj";
import { useScreenHotkeys } from "@/components/Hotkeys";
import { MethodScreen } from "@/components/MethodScreen";
import { PartidosScreen } from "@/components/PartidosScreen";
import { PresencaScreen } from "@/components/PresencaScreen";
import { VereadoresExplorer } from "@/components/VereadoresExplorer";
import { VotacoesExplorer } from "@/components/VotacoesExplorer";
import { EmptyState, Panel, Screen, Stat } from "@/components/ui";
import { displayName, formatInt, formatPct, getCore, getVereadores, getVotacoes, presencaYears, type Eleicao, type Vereador } from "@/lib/static-api";
import { dataUrl } from "@/lib/uf";
import { useCity } from "@/lib/use-city";

/**
 * Telas dos municípios do Estado do Rio. Onde a câmara publica dados legíveis (SAPL), as telas são
 * as mesmas das capitais; onde não publica, a tela Vereadores mostra a lista do TSE e as demais
 * dizem uma vez o que falta.
 */

const ANOS = ["2024", "2020"] as const;
const SITUACAO: Record<Eleicao["situacao"], string> = { eleito: "eleito", suplente: "suplente", nao_eleito: "não eleito" };

function semVotacoes(): boolean {
  return getVotacoes().length === 0;
}

export function VereadoresPage() {
  const nivel = getCore().municipio?.nivel;
  return nivel === 0 ? <VereadoresTse /> : <VereadoresExplorer />;
}

export function VotacoesPage() {
  return semVotacoes() ? <SemDado titulo="Votações">Esta câmara não publica votações em formato legível.</SemDado> : <VotacoesExplorer />;
}

export function PresencaPage() {
  return presencaYears().length === 0 ? <SemDado titulo="Presença">Esta câmara não publica a presença em plenário em formato legível.</SemDado> : <PresencaScreen />;
}

export function PartidosPage() {
  return semVotacoes() ? <PartidosTse /> : <PartidosScreen />;
}

export function MetodoPage() {
  return <MethodScreen />;
}

function SemDado({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  const { city } = useCity();
  return (
    <Screen columns="minmax(0, 1fr)" rows="minmax(0, 1fr)">
      <Panel title={<b>{titulo}</b>} aside={<span className="text-[10px] tracking-[0.14em] text-ash">{city.nome}</span>}>
        <div className="grid h-full place-items-center">
          <p className="serif max-w-[44ch] text-center text-[17px] leading-7 text-ink">{children}</p>
        </div>
      </Panel>
    </Screen>
  );
}

function eleitoEm(vereador: Vereador, ano: string): boolean {
  return vereador.eleicoes?.[ano]?.situacao === "eleito";
}

type Escopo = "eleitos2024" | "eleitos2020" | "suplentes2024" | "todos";
const ESCOPOS: Array<{ value: Escopo; label: string }> = [
  { value: "eleitos2024", label: "Eleitos em 2024" },
  { value: "eleitos2020", label: "Eleitos em 2020" },
  { value: "suplentes2024", label: "Suplentes de 2024" },
  { value: "todos", label: "Todos" }
];
type Ordem = "votos" | "nome";

function votosDe(vereador: Vereador, escopo: Escopo): number {
  const ano = escopo === "eleitos2020" ? "2020" : "2024";
  return vereador.eleicoes?.[ano]?.votos ?? (escopo === "todos" ? vereador.eleicoes?.["2020"]?.votos ?? 0 : 0);
}

function iniciais(vereador: Vereador): string {
  return displayName(vereador)
    .split(" ")
    .filter((part) => part.length > 2)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

/** Vereadores pelo TSE: eleitos e suplentes de 2020 e 2024, com partido e votos. */
export function VereadoresTse() {
  const { city } = useCity();
  const core = getCore();
  const all = getVereadores();
  const eleicoes = core.eleicoes ?? {};
  const [escopo, setEscopo] = useState<Escopo>("eleitos2024");
  const [ordem, setOrdem] = useState<Ordem>("votos");
  const [partido, setPartido] = useState("all");
  const partidos = useMemo(() => [...new Set(all.map((item) => item.partido).filter((item): item is string => Boolean(item)))].sort((a, b) => a.localeCompare(b, "pt-BR")), [all]);
  const rows = useMemo(
    () =>
      all
        .filter((item) =>
          escopo === "eleitos2024" ? eleitoEm(item, "2024") : escopo === "eleitos2020" ? eleitoEm(item, "2020") : escopo === "suplentes2024" ? item.eleicoes?.["2024"]?.situacao === "suplente" : true
        )
        .filter((item) => partido === "all" || item.partido === partido)
        .sort((a, b) => (ordem === "nome" ? displayName(a).localeCompare(displayName(b), "pt-BR") : votosDe(b, escopo) - votosDe(a, escopo))),
    [all, escopo, ordem, partido]
  );
  const [selectedId, setSelectedId] = useState("");
  const selected = rows.find((item) => item.id === selectedId) ?? rows[0] ?? all[0];
  const index = Math.max(0, rows.findIndex((item) => item.id === selected?.id));

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("v");
    if (id && all.some((item) => item.id === id)) {
      const vereador = all.find((item) => item.id === id)!;
      if (!eleitoEm(vereador, "2024")) {
        setEscopo("todos");
      }
      setSelectedId(id);
    }
  }, [all]);

  const hotkeys = useMemo(
    () => ({
      ArrowUp: () => setSelectedId(rows[(index - 1 + rows.length) % rows.length]?.id ?? ""),
      ArrowDown: () => setSelectedId(rows[(index + 1) % rows.length]?.id ?? ""),
      ArrowLeft: () => setOrdem((current) => (current === "votos" ? "nome" : "votos")),
      ArrowRight: () => setOrdem((current) => (current === "votos" ? "nome" : "votos")),
      e: () => setEscopo((current) => ESCOPOS[(ESCOPOS.findIndex((item) => item.value === current) + 1) % ESCOPOS.length].value)
    }),
    [index, rows]
  );
  useScreenHotkeys(hotkeys);

  if (!selected) {
    return <EmptyState>SEM VEREADORES</EmptyState>;
  }
  const ultima = selected.eleicoes?.["2024"] ?? selected.eleicoes?.["2020"];
  const anoUltima = selected.eleicoes?.["2024"] ? "2024" : "2020";
  const sistema = core.municipio?.sistema;

  return (
    <Screen columns="320px minmax(0, 1fr) minmax(0, 1fr)" rows="auto minmax(0, 1fr)">
      <Panel title={<b>Vereadores</b>} aside={<span className="text-[10px] tracking-[0.14em] text-ash">{rows.length}</span>} flush fill style={{ gridRow: "1 / span 2" }}>
        <div className="grid grid-cols-2 gap-2 border-b border-line p-2">
          <select className="yearselect col-span-2" aria-label="Eleição" value={escopo} onChange={(event) => setEscopo(event.target.value as Escopo)}>
            {ESCOPOS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
          <select className="yearselect" aria-label="Partido" value={partido} onChange={(event) => setPartido(event.target.value)}>
            <option value="all">Partidos</option>
            {partidos.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <select className="yearselect" aria-label="Ordem" value={ordem} onChange={(event) => setOrdem(event.target.value as Ordem)}>
            <option value="votos">Por votos</option>
            <option value="nome">Por nome</option>
          </select>
        </div>
        {rows.length === 0 ? (
          <EmptyState>NINGUÉM NESTE FILTRO</EmptyState>
        ) : (
          <ul className="menu" role="listbox" aria-label="Vereadores">
            {rows.map((vereador) => (
              <li key={vereador.id} role="presentation">
                <button type="button" role="option" aria-selected={vereador.id === selected.id} onClick={() => setSelectedId(vereador.id)}>
                  <span className="whitespace-normal break-words">
                    {displayName(vereador)}
                    <span className="faint ml-1.5 text-[10px] tracking-[0.08em]">{vereador.partido}</span>
                  </span>
                  <span className="num">{ordem === "votos" ? formatInt(votosDe(vereador, escopo)) : ""}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel
        title={
          <span className="flex items-center gap-3">
            {selected.foto ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={dataUrl(city, selected.foto)} alt="" className="photo photo--sm" loading="lazy" />
            ) : (
              <span className="photo photo--sm grid place-items-center text-[12px] tracking-[0.1em] text-ash" aria-hidden="true">
                {iniciais(selected)}
              </span>
            )}
            <span>
              <b className="serif text-[16px]">{displayName(selected)}</b>
              <span className="mt-0.5 block text-[10.5px] tracking-[0.12em] text-ash">
                {[selected.partido, ultima ? `${SITUACAO[ultima.situacao]} em ${anoUltima}` : null, selected.nome !== displayName(selected) ? selected.nome : null].filter(Boolean).join(" · ")}
              </span>
            </span>
          </span>
        }
        style={{ gridColumn: "2 / span 2" }}
      >
        <div className="grid grid-cols-2 gap-x-8">
          {ANOS.map((ano) => {
            const eleicao = selected.eleicoes?.[ano];
            const total = eleicoes[ano]?.votos_nominais ?? 0;
            return (
              <div key={ano}>
                <Stat label={`Votos em ${ano}`} value={eleicao ? formatInt(eleicao.votos) : "–"} sub={eleicao ? `${eleicao.partido} ${eleicao.numero}` : "não concorreu ou ficou fora da lista"} />
                <Stat label={`Parcela dos votos nominais de ${ano}`} value={eleicao && total ? formatPct(eleicao.votos / total, 1) : "–"} />
                <Stat label="Situação" value={eleicao ? SITUACAO[eleicao.situacao] : "–"} />
              </div>
            );
          })}
        </div>
      </Panel>

      <Panel title={<b>Eleições</b>} flush>
        <table className="ruled">
          <thead>
            <tr>
              <th>Ano</th>
              <th className="right">Cadeiras</th>
              <th className="right">Candidatos</th>
              <th className="right">Votos nominais</th>
            </tr>
          </thead>
          <tbody>
            {ANOS.map((ano) => (
              <tr key={ano}>
                <td className="num">{ano}</td>
                <td className="num right">{formatInt(eleicoes[ano]?.cadeiras)}</td>
                <td className="num right">{formatInt(eleicoes[ano]?.candidatos)}</td>
                <td className="num right">{formatInt(eleicoes[ano]?.votos_nominais)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <Panel
        title={<b>Câmara</b>}
        aside={
          core.municipio?.url_camara ? (
            <a href={core.municipio.url_camara} target="_blank" rel="noreferrer" className="btn !h-7 !px-2 text-[10px]">
              Site
            </a>
          ) : null
        }
      >
        <p className="serif text-[15px] leading-6 text-ink">Esta câmara não publica votações, presença ou proposições em formato legível.</p>
        <div className="mt-3">
          <Stat label="Sistema" value={sistemaLabel(sistema)} />
        </div>
      </Panel>
    </Screen>
  );
}

/** Partidos sem votações: cadeiras conquistadas em 2024 e 2020. */
export function PartidosTse() {
  const all = getVereadores();
  const cadeiras = (ano: string) => {
    const counts = new Map<string, { cadeiras: number; votos: number }>();
    for (const vereador of all) {
      const eleicao = vereador.eleicoes?.[ano];
      if (eleicao?.situacao === "eleito") {
        const row = counts.get(eleicao.partido) ?? { cadeiras: 0, votos: 0 };
        row.cadeiras += 1;
        row.votos += eleicao.votos;
        counts.set(eleicao.partido, row);
      }
    }
    return [...counts.entries()]
      .sort((a, b) => b[1].cadeiras - a[1].cadeiras || b[1].votos - a[1].votos)
      .map(([sigla, row]) => ({ key: sigla, label: sigla, sub: `${formatInt(row.votos)} votos dos eleitos`, value: row.cadeiras }));
  };
  return (
    <Screen columns="minmax(0, 1fr) minmax(0, 1fr)" rows="minmax(0, 1fr)">
      {ANOS.map((ano) => (
        <Panel key={ano} title={<b>Cadeiras por partido, eleição de {ano}</b>} flush fill>
          <BarList rows={cadeiras(ano)} empty="SEM ELEITOS" />
        </Panel>
      ))}
    </Screen>
  );
}
