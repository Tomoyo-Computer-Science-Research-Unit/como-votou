"""Parser for the monthly attendance table (frequencia-dos-vereadores)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class PresencaMensal:
    ano: int
    mes: int
    vereador_nome: str
    faltas: int
    faltas_abonadas: int
    total_faltas: int


@dataclass(frozen=True)
class PresencaPagina:
    ano: int
    mes: int
    atualizado_em: str | None
    linhas: list[PresencaMensal]
    observacoes: list[str]


def parse_frequencia(html: str, ano: int, mes: int) -> PresencaPagina:
    soup = BeautifulSoup(html, "lxml")
    linhas: list[PresencaMensal] = []
    for tr in soup.select("table tr"):
        tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(tds) == 4 and tds[1].isdigit() and tds[2].isdigit() and tds[3].isdigit():
            linhas.append(PresencaMensal(ano, mes, tds[0], int(tds[1]), int(tds[2]), int(tds[3])))
    text = soup.get_text(" ", strip=True)
    m = re.search(r"atualizadas pela última vez em (\d{2}/\d{2}/\d{4})", text)
    obs = re.findall(r"Considerada a presença d[ao] Sra?\.? Vereadora? ([^()]+?) \(Proc\. ([\d/]+)\)", text)
    return PresencaPagina(ano, mes, m.group(1) if m else None, linhas,
                          [f"{n.strip()} (Proc. {p})" for n, p in obs])
