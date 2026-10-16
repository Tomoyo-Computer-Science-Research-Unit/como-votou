"use client";

import { formatInt } from "@/lib/static-api";
import { cityConfig } from "@/lib/uf";
import { useCity, useLoadedCore } from "@/lib/use-city";

const HINTS: Record<string, Array<[string, string]>> = {
  "/": [
    ["↑↓", "vereador"],
    ["←→", "ordem"],
    ["v", "votos / proposições"],
    ["e", "em exercício / todos"]
  ],
  "/votacoes": [
    ["↑↓", "votação"],
    ["←→", "ano"],
    ["r", "resultado"]
  ],
  "/presenca": [
    ["←→", "ano"],
    ["↑↓", "ordem"]
  ],
  "/partidos": [["↑↓", "partido"]],
  "/metodologia": []
};

const HINTS_TSE: Array<[string, string]> = [
  ["↑↓", "vereador"],
  ["←→", "ordem"],
  ["e", "eleição"]
];

export function StatusBar() {
  const { city, screen } = useCity();
  const core = useLoadedCore();
  const hints = city.kind === "municipio" && city.nivel === 0 ? (screen === "/" ? HINTS_TSE : []) : HINTS[screen] ?? [];
  const nome = cityConfig(city).camaraCurta;
  const latestLabel =
    city.kind === "municipio"
      ? `${nome} · nível ${city.nivel}`
      : core
        ? `${nome} · ${formatInt(core.votacoes.length)} votações nominais`
        : nome;

  return (
    <footer className="statusbar">
      <span className="flex items-center gap-4">
        {hints.map(([key, label]) => (
          <span key={key}>
            <span className="kbd">{key}</span>
            {label}
          </span>
        ))}
        <span>
          <span className="kbd">1–5</span>telas
        </span>
        <span>
          <span className="kbd">u</span>cidade
        </span>
        <span>
          <span className="kbd">t</span>tema
        </span>
        <span>
          <span className="kbd">f</span>efeitos
        </span>
      </span>
      <span className="num">{latestLabel}</span>
    </footer>
  );
}
