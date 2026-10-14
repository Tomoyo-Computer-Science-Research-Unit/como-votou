"""Parsers for the Câmara Municipal de São Paulo (CMSP) open data.

Every source here carries the SPLegis parliamentary id (``IDParlamentar`` / ``chave`` /
``_cmsp_vereador_consulta_splegis_id``), so no name matching is needed to join them.

- VOTACOES_<ano>.xml          (blob storage behind the "Votação em Plenário" page): every vote of
                              the year by session; nominal ones list each vereador with party and vote
- Presencas.html              (same storage): the session tree, one ``data_app_id`` per session
- PRESENCAS_<dd_mm_aaaa>_<Tipo>_<n>.xml: one session, one row per seat-holder with the presence mark
- ws2.asmx/*JSON              (SPLegis web service): vereadores with mandates and party affiliations,
                              proposições per year and type with their authors
- wp-json/wp/v2/vereador      (portal WordPress): display name, photo and page of each vereador
"""
from __future__ import annotations

import html as htmllib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

# --- session tree ------------------------------------------------------------------------------

_SESSAO_ID = re.compile(r'data_app_id="SESSAO (\d{2})_(\d{2})_(\d{4}) (\d+)ª Sessão ([^"]+)"')


@dataclass(frozen=True)
class SessaoRef:
    data: str     # YYYY-MM-DD
    numero: int
    tipo: str     # "Ordinária", "Extraordinária", ...

    @property
    def nome(self) -> str:
        return f"{self.numero}ª Sessão {self.tipo}"

    @property
    def arquivo(self) -> str:
        """Base name used by the portal: PRESENCAS_<arquivo>.xml / VOTACOES_<arquivo>.xml."""
        y, m, d = self.data.split("-")
        return f"{d}_{m}_{y}_{self.tipo}_{self.numero}"

    @property
    def key(self) -> tuple[str, str, int]:
        return (self.data, self.tipo, self.numero)


def parse_session_tree(text: str) -> list[SessaoRef]:
    """Sessions listed in Presencas.html / Votacoes.html (jsTree ``data_app_id="SESSAO dd_mm_aaaa Nª Sessão Tipo"``)."""
    out: dict[tuple, SessaoRef] = {}
    for d, m, y, n, tipo in _SESSAO_ID.findall(text):
        s = SessaoRef(f"{y}-{m}-{d}", int(n), tipo.strip())
        out[s.key] = s
    return sorted(out.values(), key=lambda s: (s.data, s.tipo, s.numero))


# --- presence per session -------------------------------------------------------------------

def presence_status(mark: str | None) -> str:
    """Normalise the presence mark printed by the portal.

    ``Presente`` -> presente; ``*`` -> fora (suplente not in office that day, or resigned);
    ``Licença<sup>n</sup>`` -> licenca; ``Justificada…`` -> justificada; blank -> falta.
    """
    m = htmllib.unescape(mark or "").strip()
    low = m.lower()
    if low.startswith("presente"):
        return "presente"
    if m == "*":
        return "fora"
    if low.startswith("licen"):
        return "licenca"
    if low.startswith("justific"):
        return "justificada"
    if not m or low.startswith("ausente") or low.startswith("falta"):
        return "falta"
    return "outro"


@dataclass
class PresencaSessao:
    data: str
    tipo: str
    numero: int
    nome: str
    linhas: list[dict] = field(default_factory=list)   # {id, nome, partido, marca, status}


def parse_presenca_sessao(xml_text: str) -> PresencaSessao:
    root = ET.fromstring(xml_text.lstrip("\ufeff").encode("utf-8"))
    head = root.find("Presencas")
    d, m, y = (head.get("Data") or "").split("/")
    out = PresencaSessao(data=f"{y}-{m}-{d}", tipo=head.get("TipoDaSessao") or "", numero=int(head.get("NumeroDaSessao") or 0),
                         nome=head.get("NomeDaSessao") or "")
    for v in root.findall("Vereador"):
        marca = v.get("Presenca")
        out.linhas.append({"id": v.get("IDParlamentar"), "nome": (v.get("Nome") or "").strip(), "partido": (v.get("Partido") or "").strip() or None,
                           "marca": marca, "status": presence_status(marca)})
    return out


# --- votes ---------------------------------------------------------------------------------------

VOTO_MAP = {"sim": "sim", "não": "nao", "nao": "nao", "abstenção": "abstencao", "abstencao": "abstencao"}
_PROP = re.compile(r"\b(PLO|PDL|PL|PR|RDP|RPP|RDS|RPS|DOCREC)\s*(\d+)\s*[/-]\s*(\d{2,4})\b", re.I)


@dataclass
class VotacaoNominal:
    votacao_id: str
    data: str
    sessao_nome: str
    sessao_tipo: str
    sessao_numero: int
    materia: str
    ementa: str
    resultado_raw: str
    notas: str
    presentes: int | None
    impresso: dict[str, int]                 # Sim/Nao/Abstencao/Branco as printed
    votos: list[dict]                        # {id, nome, partido, voto}


def _int(s: str | None) -> int | None:
    try:
        return int(str(s).strip())
    except (TypeError, ValueError):
        return None


def parse_votacoes_ano(xml_text: str, tipo: str = "Nominal") -> list[VotacaoNominal]:
    """VOTACOES_<ano>.xml: <Sessao Nome Data><Votacao TipoVotacao ...><Vereador IDParlamentar Partido Voto/></Votacao></Sessao>."""
    root = ET.fromstring(xml_text.lstrip("\ufeff").encode("utf-8"))
    out: list[VotacaoNominal] = []
    for s in root.findall("Sessao"):
        nome = (s.get("Nome") or "").strip()
        d, m, y = (s.get("Data") or "").split("/")
        mt = re.match(r"(\d+)ª Sessão (.+)", nome)
        for v in s.findall("Votacao"):
            if tipo and (v.get("TipoVotacao") or "").strip() != tipo:
                continue
            votos = []
            for e in v.findall("Vereador"):
                votos.append({"id": e.get("IDParlamentar"), "nome": (e.get("Nome") or "").strip(),
                              "partido": (e.get("Partido") or "").strip() or None,
                              "voto": VOTO_MAP.get((e.get("Voto") or "").strip().lower(), (e.get("Voto") or "").strip().lower())})
            out.append(VotacaoNominal(
                votacao_id=v.get("VotacaoID") or "", data=f"{y}-{m}-{d}", sessao_nome=nome,
                sessao_tipo=mt.group(2).strip() if mt else "", sessao_numero=int(mt.group(1)) if mt else 0,
                materia=re.sub(r"\s+", " ", v.get("Materia") or "").strip(), ementa=re.sub(r"\s+", " ", v.get("Ementa") or "").strip(),
                resultado_raw=(v.get("Resultado") or "").strip(), notas=(v.get("NotasRodape") or "").strip(),
                presentes=_int(v.get("Presentes")),
                impresso={"sim": _int(v.get("Sim")) or 0, "nao": _int(v.get("Nao")) or 0,
                          "abstencao": _int(v.get("Abstencao")) or 0, "branco": _int(v.get("Branco")) or 0},
                votos=votos))
    return out


def resultado_of(raw: str) -> str | None:
    """'Aprovado' -> aprovado; 'Reprovado'/'Rejeitado' -> rejeitado; 'Sem quórum…' -> sem_quorum;
    'Pendente de Votação' -> pendente (the roll call did not reach the quorum and the matter stays on the agenda);
    'Eleito X' -> eleito."""
    low = raw.lower()
    if low.startswith("aprovad"):
        return "aprovado"
    if low.startswith("reprovad") or low.startswith("rejeitad"):
        return "rejeitado"
    if low.startswith("sem qu"):
        return "sem_quorum"
    if low.startswith("pendente"):
        return "pendente"
    if low.startswith("eleit"):
        return "eleito"
    if low.startswith("prejudicad"):
        return "prejudicado"
    return None


def proposicao_of(materia: str) -> tuple[str, int, int] | None:
    """First 'PL 177 /2025', 'PLO 08/2017', 'RDP 13 /2025' in the subject line -> (tipo, numero, ano)."""
    m = _PROP.search(materia)
    if not m:
        return None
    tipo, num, ano = m.group(1).upper(), int(m.group(2)), int(m.group(3))
    if ano < 100:
        ano += 2000
    return tipo, num, ano


def objeto_of(materia: str, notas: str, ementa: str = "") -> str:
    """What was voted, from the subject line the painel prints.

    redacao_final, emenda (amendments and blocks of amendments), veto, substitutivo (a PL voted
    in the form of a committee substitute), projeto, contas (TCM opinion on the mayor's accounts),
    parecer (other committee opinions voted in plenary), eleicao (Mesa), requerimento (adjournments, suspensions, agenda changes, CPIs and other motions).
    """
    low = materia.lower()
    if low.startswith("redação final") or low.startswith("redacao final"):
        return "redacao_final"
    if re.match(r"(cria|criação|criacao|adiamento|suspensão|suspensao|prorroga|encerramento|considerar|leitura|invers|inverte"
                r"|inclusão|inclusao|redução|reducao|requerimento|instalação|instalacao|retirada|votação anulada|agrupamento)", low):
        return "requerimento"
    if re.search(r"\bvetos?\b", low):
        return "veto"
    if re.search(r"\b(emenda|emendas|bloco)\b", low):
        return "emenda"
    if low.startswith("eleição") or low.startswith("eleicao"):
        return "eleicao"
    if re.match(r"(pl|plo|pdl|pr)\s*\d", low):
        return "substitutivo" if notas.strip().upper().startswith("SUBSTITUTIVO") else "projeto"
    if low.startswith("docrec") or "tribunal de contas" in low or ("parecer" in low and "contas" in f"{low} {ementa.lower()}"):
        return "contas"
    if "parecer" in low:
        return "parecer"
    return "requerimento"


def fase_of(notas: str) -> str | None:
    """'FASE DA DISCUSSÃO: 2ª' / 'volta em 2º' / 'Vai à sanção' -> '1ª discussão' / '2ª discussão'."""
    up = notas.upper()
    m = re.search(r"FASE DA DISCUSS[ÃA]O:\s*(\d)", up)
    if m:
        return f"{m.group(1)}ª discussão"
    if re.search(r"VOLTA EM 2", up):
        return "1ª discussão"
    if re.search(r"VAI [ÀA] (SANÇÃO|SANCAO|PROMULGA|REDA)", up):
        return "2ª discussão"
    return None


# --- SPLegis web service ------------------------------------------------------------------------

def mandate_years(mandatos: list[dict]) -> list[tuple[str, str]]:
    return [((m.get("inicio") or "")[:10], (m.get("fim") or "9999-12-31")[:10]) for m in mandatos or []]


def party_on(filiacoes: list[dict], date: str) -> str | None:
    """Party (sigla) of the latest affiliation that started on or before ``date``."""
    best = None
    for f in sorted(filiacoes or [], key=lambda f: f.get("inicio") or ""):
        if (f.get("inicio") or "")[:10] <= date:
            best = (f.get("partido") or {}).get("sigla")
    return best


def parse_autores(rows: list[dict]) -> dict[tuple[str, int, int], list[dict]]:
    """ProjetosAutoresJSON -> {(tipo, numero, ano): [{chave, nome}]}."""
    out: dict[tuple[str, int, int], list[dict]] = {}
    for r in rows or []:
        key = ((r.get("tipo") or "").strip(), int(r.get("numero") or 0), int(r.get("ano") or 0))
        out[key] = [{"chave": a.get("chave"), "nome": (a.get("nome") or "").strip()} for a in r.get("autores") or []]
    return out


# --- portal (WordPress) --------------------------------------------------------------------------

def parse_wp_vereadores(rows: list[dict]) -> dict[str, dict]:
    """wp-json/wp/v2/vereador -> {splegis_id: {nome, foto_url, link, slug, suplente}}."""
    out: dict[str, dict] = {}
    for r in rows or []:
        meta = r.get("meta_all") or {}
        sid = ((meta.get("_cmsp_vereador_consulta_splegis_id") or [""])[0] or "").strip()
        if not sid:
            continue
        nome = ((meta.get("_cmsp_vereador_name") or [""])[0] or "").strip() or htmllib.unescape((r.get("title") or {}).get("rendered", "")).strip()
        out.setdefault(sid, {"nome": nome, "foto_url": ((meta.get("_cmsp_vereador_image") or [""])[0] or "").strip() or None,
                             "link": r.get("link"), "slug": r.get("slug"),
                             "suplente": ((meta.get("_cmsp_vereador_suplente") or [""])[0] or "") == "on",
                             "modified": r.get("modified")})
    return out


def parse_membros(text: str) -> list[str]:
    """/vereadores/membros/: slugs of the vereadores in office (the 55 cards)."""
    return list(dict.fromkeys(re.findall(r'href="https://www\.saopaulo\.sp\.leg\.br/vereador/([a-z0-9-]+)/"', text)))


def veto_resultado(materia: str, resultado: str | None) -> str | None:
    """Votes on vetoes are phrased as 'Rejeição aos vetos' or 'Manutenção aos vetos'; turn the
    approval of that motion into what happened to the veto (derrubado / mantido)."""
    low = materia.lower()
    if resultado not in ("aprovado", "rejeitado"):
        return resultado
    if low.startswith("rejei"):
        return "derrubado" if resultado == "aprovado" else "mantido"
    if low.startswith("manuten"):
        return "mantido" if resultado == "aprovado" else "derrubado"
    return resultado
