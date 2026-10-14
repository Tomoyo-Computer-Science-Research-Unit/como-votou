"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useScreenHotkeys } from "@/components/Hotkeys";
import { EmptyState, Panel, Screen, Segmented } from "@/components/ui";
import { displayName, formatInt, getVereadores, presencaYears } from "@/lib/static-api";

const MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
type Sort = "total" | "nome";

export function PresencaScreen() {
  const years = presencaYears();
  const [year, setYear] = useState(years[0] ?? new Date().getFullYear());
  const [sort, setSort] = useState<Sort>("total");

  const rows = useMemo(
    () =>
      getVereadores()
        .map((vereador) => {
          const meses = MONTHS.map((_, index) => vereador.presenca?.por_mes?.[`${year}-${String(index + 1).padStart(2, "0")}`] ?? null);
          const ano = vereador.presenca?.por_ano?.[String(year)];
          return { vereador, meses, total: ano?.total ?? 0, abonadas: ano?.abonadas ?? 0, apurados: meses.filter(Boolean).length };
        })
        .filter((row) => row.apurados > 0)
        .sort((a, b) => (sort === "nome" ? displayName(a.vereador).localeCompare(displayName(b.vereador), "pt-BR") : b.total - a.total || a.vereador.nome.localeCompare(b.vereador.nome))),
    [sort, year]
  );

  const hotkeys = useMemo(
    () => ({
      ArrowLeft: () => setYear((current) => years[(years.indexOf(current) + 1) % years.length] ?? current),
      ArrowRight: () => setYear((current) => years[(years.indexOf(current) - 1 + years.length) % years.length] ?? current),
      ArrowUp: () => setSort((current) => (current === "total" ? "nome" : "total")),
      ArrowDown: () => setSort((current) => (current === "total" ? "nome" : "total"))
    }),
    [years]
  );
  useScreenHotkeys(hotkeys);

  return (
    <Screen columns="minmax(0, 1fr)" rows="minmax(0, 1fr)">
      <Panel
        title={
          <span>
            <b>Faltas em plenário</b> · {year}
          </span>
        }
        aside={
          <>
            <Segmented label="Ano" value={String(year)} options={years.map((item) => ({ value: String(item), label: String(item) }))} onChange={(value) => setYear(Number(value))} />
            <Segmented
              label="Ordem"
              value={sort}
              options={[
                { value: "total", label: "Faltas" },
                { value: "nome", label: "Nome" }
              ]}
              onChange={setSort}
            />
          </>
        }
        flush
        fill
      >
        {rows.length === 0 ? (
          <EmptyState>SEM PRESENÇA APURADA NESTE ANO</EmptyState>
        ) : (
          <table className="ruled">
            <thead>
              <tr>
                <th>Vereador</th>
                <th>Partido</th>
                {MONTHS.map((month) => (
                  <th key={month} className="right">
                    {month}
                  </th>
                ))}
                <th className="right">Total</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.vereador.id}>
                  <td className="max-w-[220px] whitespace-normal break-words">
                    <Link href={`/?v=${encodeURIComponent(row.vereador.id)}`} className="text-ink hover:underline hover:underline-offset-4">
                      {displayName(row.vereador)}
                    </Link>
                  </td>
                  <td className="faint">{row.vereador.partido}</td>
                  {row.meses.map((mes, index) => (
                    <td
                      key={index}
                      className={`num right ${mes === null ? "faint" : ""}`}
                      style={mes && mes.total ? { background: `color-mix(in srgb, var(--ink) ${Math.min(60, mes.total * 12)}%, transparent)`, color: mes.total >= 4 ? "var(--paper)" : undefined } : undefined}
                      title={mes ? `${mes.total} faltas, ${mes.abonadas} abonadas` : "sem apuração"}
                    >
                      {mes === null ? "·" : mes.total === 0 ? "" : mes.abonadas ? `${mes.total} (${mes.abonadas})` : mes.total}
                    </td>
                  ))}
                  <td className="num right">
                    {row.total}
                    {row.abonadas ? <span className="faint"> ({row.abonadas})</span> : null}
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
