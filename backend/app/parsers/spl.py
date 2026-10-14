"""Parsers for the SPL (Lotus Domino) ?ReadViewEntries&OutputFormat=JSON views."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterator

TIPO_BY_VIEW = {
    "vlei": "PL", "vleicomp": "PLC", "vdecreto": "PDL", "vemenda": "PELOM",
    "vresolucao": "PR", "vreqinf": "REQINF", "vreq": "REQ", "vindicacao": "IND",
    "vmocao": "MOC", "voficio": "OFI", "vmensagem": "MSG",
}
_SPLIT = re.compile(r"\s*=>\s*")


@dataclass(frozen=True)
class Proposicao:
    id: str            # "<tipo>-<numero>/<ano>"
    tipo: str
    numero: str
    ano: int
    ementa: str
    data: str | None   # YYYY-MM-DD (publication/presentation date as shown in the view)
    autores: list[str]       # one entry per author, "VEREADOR"/"VEREADORA" prefix removed
    autores_raw: str         # the author column as printed
    comissoes: list[str]
    unid: str
    legislatura_db: str


def entry_values(entry: dict[str, Any]) -> list[str]:
    vals: list[str] = []
    for col in entry.get("entrydata", []):
        for key in ("text", "number", "datetime"):
            if key in col:
                v = col[key].get("0", "")
                vals.append("" if v is None else str(v))
                break
        else:
            vals.append("")
    return vals


def iter_entries(doc: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield from doc.get("viewentry", [])


def _date(s: str) -> str | None:
    m = re.match(r"(\d{4})(\d{2})(\d{2})", s or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def _authors(s: str) -> list[str]:
    """One string per author; institutional strings (committees) are kept whole."""
    from ..names import split_authors
    return split_authors(s)


def parse_proposicoes(doc: dict[str, Any], view: str, legislatura_db: str) -> list[Proposicao]:
    """Views vlei/vleicomp/...: numero/ano, code, _, ementa=>key=>{comissões}, date, autor, ..."""
    tipo = TIPO_BY_VIEW.get(view, view)
    out: list[Proposicao] = []
    for e in iter_entries(doc):
        if "@unid" not in e:
            continue
        v = entry_values(e)
        if len(v) < 6:
            continue
        numano = v[0].strip()
        m = re.match(r"(\d+)(?:-([A-Z]))?/(\d{4})", numano)
        if not m:
            continue
        numero = str(int(m.group(1))) + (f"-{m.group(2)}" if m.group(2) else "")
        ano = int(m.group(3))
        pieces = _SPLIT.split(v[3])
        ementa = pieces[0].strip()
        comissoes: list[str] = []
        if len(pieces) >= 3:
            body = pieces[2].strip().strip("{}")
            comissoes = [c.strip() for c in re.split(r"(?=Comiss(?:ão|ões) )", body) if c.strip()]
        out.append(Proposicao(
            id=f"{tipo}-{numero}/{ano}", tipo=tipo, numero=numero, ano=ano, ementa=ementa,
            data=_date(v[4]), autores=_authors(v[5]), autores_raw=v[5].strip(), comissoes=comissoes,
            unid=e["@unid"], legislatura_db=legislatura_db,
        ))
    return out
