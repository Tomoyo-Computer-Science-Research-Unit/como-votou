"""Parsers for camara.rio vereador listings (current and previous legislatures)."""
from __future__ import annotations

import html as htmllib
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

ORDINAL_LEG = re.compile(r"(\d+)ª")


@dataclass
class Vereador:
    id: str                     # "cvd:<n>" from camara.rio, stable across pages
    nome: str
    nome_parlamentar: str
    partido: str | None
    legislaturas: list[int] = field(default_factory=list)
    partidos_por_legislatura: dict[str, str] = field(default_factory=dict)
    situacao: str | None = None  # "em_exercicio" for the current list; unknown otherwise
    foto: str | None = None
    gabinete: str | None = None
    telefone: str | None = None
    email: str | None = None
    perfil_url: str | None = None


def _decode_email(a) -> str | None:
    if a is None:
        return None
    href = htmllib.unescape(a.get("href", ""))
    return href.removeprefix("mailto:").strip() or None


def parse_vereadores_atuais(html: str, legislatura: int, photo_sink=None) -> list[Vereador]:
    """vereadores_atuais.php: table Foto | Vereador | Partido | Sala | Telefone | E-mail.

    photo_sink(cvd, data_uri) -> url is called for inline base64 photos, if given.
    """
    soup = BeautifulSoup(html, "lxml")
    out: list[Vereador] = []
    for tr in soup.select("tr"):
        tds = tr.find_all("td")
        if len(tds) < 6:
            continue
        link = tds[1].find("a")
        if not link or "cvd=" not in link.get("href", ""):
            continue
        cvd = re.search(r"cvd=(\d+)", link["href"]).group(1)
        nome = link.get_text(" ", strip=True)
        img_p = tds[2].find("img")
        partido = (img_p.get("alt") or img_p.get("title") or "").strip() if img_p else None
        foto = None
        img_f = tds[0].find("img")
        if img_f and img_f.get("src"):
            src = img_f["src"]
            foto = photo_sink(cvd, src) if (photo_sink and src.startswith("data:")) else src
        out.append(Vereador(
            id=f"cvd:{cvd}", nome=nome, nome_parlamentar=nome, partido=partido or None,
            legislaturas=[legislatura], partidos_por_legislatura={str(legislatura): partido} if partido else {},
            situacao="em_exercicio", foto=foto,
            gabinete=tds[3].get_text(" ", strip=True) or None,
            telefone=tds[4].get_text(" ", strip=True) or None,
            email=_decode_email(tds[5].find("a")),
        ))
    return out


def parse_vereadores_anteriores(html: str) -> list[Vereador]:
    """/vereadores/anteriores: VEREADOR | LEGISLATURA E PARTIDO(S) ("3ª - PT<br/>4ª - PT")."""
    soup = BeautifulSoup(html, "lxml")
    out: list[Vereador] = []
    for tr in soup.select("table.TabelaPadrao tr"):
        tds = tr.find_all("td")
        if len(tds) != 2:
            continue
        a = tds[0].find("a")
        if not a or "cvd=" not in a.get("href", ""):
            continue
        cvd = re.search(r"cvd=(\d+)", a["href"]).group(1)
        nome = a.get_text(" ", strip=True)
        legs: list[int] = []
        parts: dict[str, str] = {}
        for chunk in re.split(r"<br\s*/?>", str(tds[1])):
            text = BeautifulSoup(chunk, "lxml").get_text(" ", strip=True)
            m = ORDINAL_LEG.search(text)
            if not m:
                continue
            n = int(m.group(1))
            legs.append(n)
            party = text.split("-", 1)[1].strip() if "-" in text else ""
            if party:
                parts[str(n)] = party
        out.append(Vereador(id=f"cvd:{cvd}", nome=nome, nome_parlamentar=nome, partido=None,
                            legislaturas=legs, partidos_por_legislatura=parts, situacao=None))
    return out
