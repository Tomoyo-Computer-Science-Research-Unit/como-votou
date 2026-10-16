"use client";

import Link from "next/link";
import { Panel } from "@/components/ui";
import { MUNICIPIOS, cityRoute, CIDADES } from "@/lib/uf";

export const SISTEMA_LABELS: Record<string, string> = {
  sapl3: "SAPL 3",
  sapl25: "SAPL 2.5",
  "portal-modelo": "Portal Modelo",
  "camara-sem-papel": "Câmara sem Papel",
  jcsoftwares: "JC Softwares",
  betha: "Betha",
  wordpress: "WordPress",
  proprio: "próprio",
  "proprio (Domino)": "próprio (Domino)",
  inacessivel: "fora do ar",
  "mtw-portalgov": "MTW PortalGov",
  "npi-brasil": "NPI Brasil",
  joomla: "Joomla",
  drupal: "Drupal",
  wix: "Wix",
  siscam: "Siscam",
  "processo-legislativo-eletronico": "PLE",
  spa: "aplicativo web",
  outro: "outro",
  nenhum: "sem site",
  desconhecido: "não verificado"
};

export function sistemaLabel(value: string | null | undefined): string {
  return value ? SISTEMA_LABELS[value] ?? value : "–";
}

const NIVEL = ["vereadores", "proposições", "presença", "votos"];

function host(url: string | null): string {
  if (!url) {
    return "";
  }
  try {
    return new URL(url).host.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** Os 92 municípios do Estado do Rio: sistema da câmara, nível de dado publicado aqui e o site. */
export function CoberturaRj({ current }: { current?: string }) {
  const rows = [...MUNICIPIOS].sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
  const counts = [0, 1, 2, 3].map((nivel) => rows.filter((item) => item.nivel === nivel).length);
  return (
    <Panel
      title={<b>Câmaras do Estado do Rio</b>}
      aside={<span className="text-[10px] tracking-[0.14em] text-ash">{counts.map((count, nivel) => `${NIVEL[nivel]} ${count}`).join(" · ")}</span>}
      flush
      fill
    >
      <table className="ruled ruled--tight nofx">
        <colgroup>
          <col style={{ width: "34%" }} />
          <col style={{ width: "20%" }} />
          <col style={{ width: "16%" }} />
          <col />
        </colgroup>
        <thead>
          <tr>
            <th>Município</th>
            <th>Sistema</th>
            <th>Nível</th>
            <th>Câmara</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((item) => {
            const city = item.capital ? CIDADES[0] : CIDADES.find((candidate) => candidate.key === `rj/${item.slug}`);
            return (
              <tr key={item.slug} className={item.slug === current ? "font-semibold" : undefined}>
                <td className="whitespace-normal break-words">
                  {city ? (
                    <Link href={cityRoute(city, "/")} className="text-ink hover:underline hover:underline-offset-4">
                      {item.nome}
                    </Link>
                  ) : (
                    item.nome
                  )}
                </td>
                <td className="whitespace-normal break-words">{sistemaLabel(item.sistema)}</td>
                <td className="whitespace-normal">
                  <span className="num">{item.nivel}</span> <span className="faint">{NIVEL[item.nivel]}</span>
                </td>
                <td className="whitespace-normal break-all">
                  {item.url_camara ? (
                    <a href={item.url_camara} target="_blank" rel="noreferrer" className="text-ash underline decoration-fog underline-offset-4 hover:text-ink">
                      {host(item.url_camara)}
                    </a>
                  ) : (
                    <span className="faint">–</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Panel>
  );
}
