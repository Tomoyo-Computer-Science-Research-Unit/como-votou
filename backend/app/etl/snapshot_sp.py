"""Câmara Municipal de São Paulo -> data/sp/snapshot.json (same shape as the Rio snapshot).

    python -m app.etl.export_snapshot --uf SP --all       # daily: 2021 on, refresh what can change
    python -m app.etl.export_snapshot --uf SP --offline   # rebuild from data/raw only

Sources (details and counts in FINDINGS.md, section "São Paulo"):
  votes      VOTACOES_<ano>.xml on the Câmara's blob storage, one file per year, nominal votes with
             IDParlamentar, party and vote of each vereador who voted
  presence   PRESENCAS_<dd_mm_aaaa>_<Tipo>_<n>.xml, one file per plenary session, listed by the
             session tree in Presencas.html
  roster     SPLegis web service VereadoresCMSPJSON (mandates, affiliations), OcupacaoGabineteJSON,
             the portal's WordPress pages (name, photo) and /vereadores/membros (who is in office)
  bills      SPLegis ProjetosAutoresJSON (per year and type, with author ids) and ProjetosPorAnoJSON
             (ementa and date)
All of them carry the SPLegis id, so the joins are by id, never by name.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from .. import config
from ..http import Downloader
from ..parsers.cmsp import (SessaoRef, fase_of, objeto_of, parse_autores, parse_membros, parse_presenca_sessao,
                            parse_session_tree, parse_votacoes_ano, parse_wp_vereadores, party_on, proposicao_of,
                            resultado_of, veto_resultado)
from ..parsers.vereadores import Vereador
from .aggregates import lado_vencedor, legislatura_of

UF = "SP"
LEGISLATURAS = [
    {"numero": 18, "inicio": "2021-01-01", "fim": "2024-12-31"},
    {"numero": 19, "inicio": "2025-01-01", "fim": "2028-12-31"},
]
# Proposições kept per vereador. RDS/RPS (about 2,000 a year: coauthorship requests, votes of
# praise, licence requests, agenda inclusions) and the internal document types are left out.
TIPOS = ["PL", "PDL", "PR", "PLO", "IND", "MOC", "RDP", "RPP"]
# Presence of past sessions can change when an absence is justified; re-read this many days back.
PRESENCA_REFRESH_DAYS = 45


def log(*a: object) -> None:
    print(*a, file=sys.stderr, flush=True)


def vid(chave: object) -> str:
    return f"cmsp:{int(str(chave).strip())}"


def title_name(nome: str) -> str:
    small = {"de", "da", "do", "das", "dos", "e"}
    words = []
    for i, w in enumerate(nome.lower().split()):
        words.append(w if (w in small and i) else w[:1].upper() + w[1:])
    return " ".join(words)


# --- loaders -------------------------------------------------------------------------------------

def load_sessions(dl: Downloader, refresh: bool) -> list[SessaoRef]:
    f = dl.fetch(f"{config.CMSP_BLOB}/Presencas.html", refresh=refresh)
    return parse_session_tree(f.text())


def presenca_url(s: SessaoRef) -> str:
    return f"{config.CMSP_BLOB}/PRESENCAS_{quote(s.arquivo)}.xml"


def votacoes_html_url(s: SessaoRef) -> str:
    return f"{config.CMSP_BLOB}/VOTACOES_{quote(s.arquivo)}.html"


def load_presencas(dl: Downloader, sessions: list[SessaoRef], from_year: int, refresh: bool,
                   refresh_from: str | None) -> tuple[list, list[dict]]:
    """One PresencaSessao per session from ``from_year`` on; sessions whose file is missing are listed."""
    cutoff = (date.today() - timedelta(days=PRESENCA_REFRESH_DAYS)).isoformat()
    out, missing = [], []
    for s in sessions:
        if int(s.data[:4]) < from_year:
            continue
        rf = refresh and (s.data >= cutoff or (refresh_from is not None and s.data >= refresh_from))
        try:
            f = dl.fetch(presenca_url(s), refresh=rf)
            out.append(parse_presenca_sessao(f.text()))
        except Exception as e:   # 404 (file not published) or --offline cache miss
            missing.append({"data": s.data, "sessao": s.nome, "erro": repr(e)[:160]})
    return out, missing


def monthly_presence(sessoes: list) -> list[dict]:
    """Session marks -> one row per vereador per month in the Rio contract shape.

    faltas = sessions with a blank mark (unexcused); faltas_abonadas = licença + justificada;
    total_faltas = both. Sessions marked '*' (not in office) do not count. All plenary sessions
    count, ordinárias and extraordinárias.
    """
    acc: dict[tuple[str, int, int], Counter] = defaultdict(Counter)
    nomes: dict[str, str] = {}
    for s in sessoes:
        y, m = int(s.data[:4]), int(s.data[5:7])
        for r in s.linhas:
            if r["status"] == "fora" or not r["id"]:
                continue
            c = acc[(vid(r["id"]), y, m)]
            c["sessoes"] += 1
            c[r["status"]] += 1
            nomes[vid(r["id"])] = r["nome"]
    rows = []
    for (i, y, m), c in sorted(acc.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0])):
        abon = c["licenca"] + c["justificada"]
        rows.append({"ano": y, "mes": m, "vereador_nome": nomes[i], "vereador_id": i,
                     "faltas": c["falta"], "faltas_abonadas": abon, "total_faltas": c["falta"] + abon,
                     "sessoes": c["sessoes"], "presencas": c["presente"], "licencas": c["licenca"],
                     "justificadas": c["justificada"]})
    return rows


def load_votacoes_xml(dl: Downloader, from_year: int, refresh: bool) -> tuple[list, dict]:
    now = date.today()
    out, simbolicas = [], Counter()
    for y in range(from_year, now.year + 1):
        rf = refresh and (y == now.year or (y == now.year - 1 and now.month <= 2))
        f = dl.fetch(f"{config.CMSP_BLOB}/VOTACOES_{y}.xml", refresh=rf)
        text = f.text()
        out.extend(parse_votacoes_ano(text))
        simbolicas[str(y)] = len(parse_votacoes_ano(text, tipo="Simbólica"))
    return out, dict(simbolicas)


def load_proposicoes(dl: Downloader, from_year: int, refresh: bool) -> tuple[list[dict], dict[str, int]]:
    now = date.today()
    rows: list[dict] = []
    raw_counts: dict[str, int] = {}
    for y in range(from_year, now.year + 1):
        rf = refresh and y == now.year
        try:
            meta = {(r["tipo"], int(r["numero"]), int(r["ano"])): r
                    for r in dl.fetch(f"{config.CMSP_WS}/ProjetosPorAnoJSON?Ano={y}", refresh=rf).json()}
        except FileNotFoundError as e:
            log(f"  ProjetosPorAno {y}: skipped ({e})")
            meta = {}
        for tipo in TIPOS:
            try:
                autores = parse_autores(dl.fetch(f"{config.CMSP_WS}/ProjetosAutoresJSON?ano={y}&tipo={tipo}&numero=", refresh=rf).json())
            except FileNotFoundError as e:
                log(f"  ProjetosAutores {y} {tipo}: skipped ({e})")
                continue
            raw_counts[f"{y}/{tipo}"] = len(autores)
            for (t, n, a), aut in autores.items():
                m = meta.get((t, n, a), {})
                rows.append({"id": f"{t}-{n}/{a}", "tipo": t, "numero": str(n), "ano": a,
                             "ementa": re.sub(r"\s+", " ", m.get("ementa") or "").strip(),
                             "data": (m.get("data") or "")[:10] or None,
                             "autores": [title_name(x["nome"]) for x in aut],
                             "autores_raw": ", ".join(x["nome"] for x in aut),
                             "_autores_chaves": [x["chave"] for x in aut if x.get("chave") is not None],
                             "chave": m.get("chave")})
    return rows, raw_counts


def load_vereadores(dl: Downloader, refresh: bool) -> tuple[dict, dict, list[str], dict]:
    ws = {str(x["chave"]): x for x in dl.fetch(f"{config.CMSP_WS}/VereadoresCMSPJSON", refresh=refresh).json()}
    wp_rows: list[dict] = []
    for page in range(1, 10):
        try:
            rows = dl.fetch(f"{config.CMSP_WP}?per_page=100&page={page}", refresh=refresh).json()
        except Exception:      # past the last page WordPress answers 400
            break
        if not isinstance(rows, list) or not rows:
            break
        wp_rows.extend(rows)
        if len(rows) < 100:
            break
    wp = parse_wp_vereadores(wp_rows)
    membros = parse_membros(dl.fetch(f"{config.CMSP_PORTAL}/vereadores/membros/", refresh=refresh).text())
    gab: dict[str, str] = {}
    try:
        for r in sorted(dl.fetch(f"{config.CMSP_WS}/OcupacaoGabineteJSON", refresh=refresh).json(), key=lambda r: (r.get("legislatura") or 0, r.get("inicio") or "")):
            if r.get("legislatura") == LEGISLATURAS[-1]["numero"] and r.get("codigo"):
                gab[str(r["codigo"])] = f"Gabinete {r['gabinete']}"
    except Exception as e:
        log(f"  OcupacaoGabinete: {e!r}")
    return ws, wp, membros, gab


def save_photo(dl: Downloader, url: str, chave: str, photos: Path) -> str | None:
    try:
        f = dl.fetch(url)
    except Exception as e:
        log(f"  foto {chave}: {e!r}")
        return None
    photos.mkdir(parents=True, exist_ok=True)
    ext = Path(url.split("?")[0]).suffix.lower().lstrip(".") or "jpg"
    dst = photos / f"{chave}.{ 'jpg' if ext == 'jpeg' else ext}"
    if not dst.exists() or dst.read_bytes() != f.path.read_bytes():
        dst.write_bytes(f.path.read_bytes())
    return f"photos/{dst.name}"


# --- votes -----------------------------------------------------------------------------------------

def _hora(notas: str) -> str | None:
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", notas)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def _frase(raw: str, notas: str) -> str:
    parts = [p.strip().strip('"').strip() for p in re.split(r"[\t\r\n]+", notas) if p.strip().strip('"').strip()]
    return " · ".join([raw] + parts) if parts else raw


def titulo_of(materia: str, ementa: str, objeto: str) -> str:
    """Subject line as the painel prints it, without the '...' the painel adds when it cuts the line.
    Votes on accounts get 'Contas, DOCREC <n>/<ano>' (their subject line is cut before the number)."""
    if objeto == "contas":
        m = re.search(r"DOCREC\s*-?\s*(\d+)\s*[-/]\s*(\d{4})", f"{materia} {ementa}", re.I)
        if m:
            return f"Contas, DOCREC {int(m.group(1))}/{m.group(2)}"
    return re.sub(r"\s*\.\.\.$", "", materia).strip()


def build_votacoes(xml_votes: list, sessoes: list, props: dict[str, dict], vereador_ids: set[str],
                   session_refs: dict[tuple, SessaoRef]) -> tuple[list[dict], dict]:
    pres_by_key = {(s.data, s.tipo, s.numero): s for s in sessoes}
    month_roster: dict[str, dict[str, dict]] = defaultdict(dict)
    for s in sessoes:
        for r in s.linhas:
            if r["status"] != "fora" and r["id"]:
                month_roster[s.data[:7]][vid(r["id"])] = r
    stats: dict = {"nominais": 0, "anuladas": 0, "impresso_discrepancies": [], "contagem_mismatches": 0,
                   "sessao_sem_presenca": 0, "ausentes_presentes_na_sessao": 0, "ausentes_fora_da_sessao": 0,
                   "votos_sem_cadastro": 0, "por_ano": {}}
    out: list[dict] = []
    for v in xml_votes:
        if "anulad" in v.materia.lower():
            stats["anuladas"] += 1
            continue
        stats["nominais"] += 1
        pa = stats["por_ano"].setdefault(v.data[:4], {"nominais": 0, "sem_resultado": 0})
        pa["nominais"] += 1
        votos: dict[str, str] = {}
        partidos: dict[str, str | None] = {}
        for r in v.votos:
            if not r["id"] or r["voto"] not in ("sim", "nao", "abstencao"):
                continue
            i = vid(r["id"])
            votos[i] = r["voto"]
            partidos[i] = r["partido"]
            if i not in vereador_ids:
                stats["votos_sem_cadastro"] += 1
        contagem = {k: sum(1 for x in votos.values() if x == k) for k in ("sim", "nao", "abstencao")}
        contagem["presentes_votando"] = len(votos)
        for side in ("sim", "nao", "abstencao"):
            if v.impresso.get(side, 0) != contagem[side]:
                stats["impresso_discrepancies"].append({"id": f"cmsp:{v.votacao_id}", "data": v.data, "materia": v.materia,
                                                        "lado": side, "impresso": v.impresso.get(side, 0), "nomes": contagem[side]})
        # Who was in office at this session, from the session's own presence list.
        sess = pres_by_key.get((v.data, v.sessao_tipo, v.sessao_numero))
        roster_label = None
        if sess is not None:
            roster = {vid(r["id"]): r for r in sess.linhas if r["status"] != "fora" and r["id"]}
            roster_label = f"sessão {v.sessao_nome} de {v.data}"
        else:
            stats["sessao_sem_presenca"] += 1
            roster = month_roster.get(v.data[:7], {})
            roster_label = v.data[:7] if roster else None
        sem_voto_presentes = []
        for i, r in roster.items():
            if i in votos:
                continue
            votos[i] = "ausente"
            partidos.setdefault(i, r.get("partido"))
            if sess is not None:
                if r["status"] == "presente":
                    stats["ausentes_presentes_na_sessao"] += 1
                    sem_voto_presentes.append(i)
                else:
                    stats["ausentes_fora_da_sessao"] += 1
        parsed = proposicao_of(v.materia) or proposicao_of(v.ementa)
        objeto = objeto_of(v.materia, v.notas, v.ementa)
        prop: dict = {"id": None, "tipo": None, "numero": None, "ano": None, "ementa": v.ementa or None, "autores": [], "autores_ids": []}
        if parsed:
            t, n, a = parsed
            pid = f"{t}-{n}/{a}"
            base = props.get(pid)
            prop = {"id": pid, "tipo": t, "numero": str(n), "ano": a,
                    "ementa": v.ementa or (base or {}).get("ementa") or None,
                    "autores": list((base or {}).get("autores", [])), "autores_ids": list((base or {}).get("autores_ids", []))}
        resultado = resultado_of(v.resultado_raw)
        if objeto == "veto":
            resultado = veto_resultado(v.materia, resultado)
        if resultado is None:
            pa["sem_resultado"] += 1
        sref = session_refs.get((v.data, v.sessao_tipo, v.sessao_numero))
        out.append({
            "id": f"cmsp:{v.votacao_id}", "data": v.data, "hora": _hora(v.notas),
            "legislatura": legislatura_of(v.data, LEGISLATURAS),
            "sessao": {"tipo": None, "numero": v.sessao_nome or None, "fase": fase_of(v.notas)},
            "titulo": titulo_of(v.materia, v.ementa, objeto),
            "proposicao": prop, "objeto": objeto, "resultado": resultado,
            "resultado_frase": _frase(v.resultado_raw, v.notas),
            "lado_vencedor": lado_vencedor(contagem), "contagem": contagem,
            "presentes_painel": v.presentes, "impresso": v.impresso,
            "presidente": None, "presidente_nome": None, "roster_mes": roster_label,
            "votos": votos, "partidos": partidos, "sem_voto_presentes": sem_voto_presentes,
            "fonte": votacoes_html_url(sref) if sref else f"{config.CMSP_BLOB}/VOTACOES_{v.data[:4]}.xml",
        })
    return out, stats


# --- main ------------------------------------------------------------------------------------------

def run(args) -> int:
    refresh = not (args.offline or args.no_refresh)
    dl = Downloader(offline=args.offline)
    from_year = args.from_year
    log("SP: vereadores ...")
    ws, wp, membros, gab = load_vereadores(dl, refresh)
    log(f"  {len(ws)} in SPLegis, {len(wp)} portal pages, {len(membros)} in office on the portal")
    log("SP: sessões e presença ...")
    sessions = load_sessions(dl, refresh)
    log(f"  {len(sessions)} sessions in the tree, {sum(1 for s in sessions if int(s.data[:4]) >= args.presenca_from)} from {args.presenca_from}")
    sessoes, missing = load_presencas(dl, sessions, args.presenca_from, refresh, args.presenca_refresh_from)
    log(f"  {len(sessoes)} session presence files read, {len(missing)} missing")
    presencas = monthly_presence(sessoes)
    log("SP: votações ...")
    xml_votes, simbolicas = load_votacoes_xml(dl, from_year, refresh)
    log(f"  {len(xml_votes)} nominal votes in the yearly files ({sum(simbolicas.values())} symbolic not used)")
    log("SP: proposições ...")
    prop_rows, raw_counts = load_proposicoes(dl, from_year, refresh)
    log(f"  {len(prop_rows)} proposições ({', '.join(TIPOS)}) from {from_year}")

    # --- roster: everyone who sat (presence not '*'), voted, or authored, from from_year on --------
    seen: dict[str, dict] = {}       # id -> {legs: set, party_by_leg: {leg: (date, party)}}

    def see(i: str, data: str, partido: str | None) -> None:
        leg = legislatura_of(data, LEGISLATURAS)
        if leg is None:
            return
        e = seen.setdefault(i, {"legs": set(), "party": {}})
        e["legs"].add(leg)
        if partido and (str(leg) not in e["party"] or e["party"][str(leg)][0] <= data):
            e["party"][str(leg)] = (data, partido)

    for s in sessoes:
        for r in s.linhas:
            if r["status"] != "fora" and r["id"]:
                see(vid(r["id"]), s.data, r["partido"])
    for v in xml_votes:
        for r in v.votos:
            if r["id"]:
                see(vid(r["id"]), v.data, r["partido"])
    ws_ids = {vid(k) for k in ws}
    latest = max(sessoes, key=lambda s: (s.data, s.tipo != "Ordinária", s.numero), default=None)
    em_exercicio = {vid(r["id"]) for r in latest.linhas if r["status"] != "fora" and r["id"]} if latest else set()
    wp_slug_ids = {vid(k) for k, w in wp.items() if w.get("slug") in set(membros)}
    photos = config.photos_dir(UF)
    vereadores: list[Vereador] = []
    for i in sorted(set(seen) | (wp_slug_ids & ws_ids)):
        chave = i.split(":")[1]
        w = ws.get(chave, {})
        p = wp.get(chave, {})
        e = seen.get(i, {"legs": set(), "party": {}})
        nome = p.get("nome") or title_name(w.get("nome") or chave)
        legs = sorted(e["legs"])
        ppl = {k: val[1] for k, val in e["party"].items()}
        for leg in legs:     # fall back to the affiliation in force at the end of the legislature
            if str(leg) not in ppl:
                lg = next(x for x in LEGISLATURAS if x["numero"] == leg)
                pty = party_on(w.get("filiacoes") or [], min(lg["fim"], date.today().isoformat()))
                if pty:
                    ppl[str(leg)] = pty
        partido = ppl.get(str(legs[-1])) if legs else party_on(w.get("filiacoes") or [], date.today().isoformat())
        foto = save_photo(dl, p["foto_url"], chave, photos) if p.get("foto_url") else None
        vereadores.append(Vereador(
            id=i, nome=nome, nome_parlamentar=nome, partido=partido, legislaturas=legs, partidos_por_legislatura=ppl,
            situacao="em_exercicio" if i in em_exercicio else "fora_de_exercicio", foto=foto,
            gabinete=gab.get(chave) if i in em_exercicio else None, perfil_url=p.get("link")))
    ids = {v.id for v in vereadores}
    log(f"  {len(vereadores)} vereadores from {from_year} ({len(em_exercicio)} in office at the session of {latest.data if latest else '?'};"
        f" {len(membros)} cards on /vereadores/membros)")

    # --- proposições: author ids ---------------------------------------------------------------
    unmatched_authors: Counter = Counter()
    for r in prop_rows:
        r["autores_ids"] = [vid(c) for c in r.pop("_autores_chaves") if vid(c) in ids]
        r["autores_outros"] = False
        r.pop("chave", None)
        if not r["autores_ids"]:
            for a in r["autores_raw"].split(", "):
                unmatched_authors[a] += 1
    props = {r["id"]: r for r in prop_rows}

    # --- votes -----------------------------------------------------------------------------------
    session_refs = {s.key: s for s in sessions}
    votacoes, vstats = build_votacoes(xml_votes, sessoes, props, ids, session_refs)
    # Authors of voted bills presented before from_year: one SPLegis call each (cached forever).
    for vt in votacoes:
        p = vt["proposicao"]
        if p["id"] and not p["autores"] and p["tipo"] in ("PL", "PDL", "PR", "PLO", "RDP", "RPP"):
            try:
                rows = dl.fetch(f"{config.CMSP_WS}/ProjetosAutoresJSON?ano={p['ano']}&tipo={p['tipo']}&numero={p['numero']}").json()
                aut = parse_autores(rows).get((p["tipo"], int(p["numero"]), int(p["ano"])), [])
                p["autores"] = [title_name(x["nome"]) for x in aut]
                p["autores_ids"] = [vid(x["chave"]) for x in aut if x.get("chave") is not None and vid(x["chave"]) in ids]
            except Exception as e:
                log(f"  autores {p['id']}: {e!r}")
    log(f"  {len(votacoes)} votações nominais; {len(vstats['impresso_discrepancies'])} printed-count differences;"
        f" {vstats['sessao_sem_presenca']} without a session presence file")

    snapshot = {
        "uf": UF,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "legislatures": LEGISLATURAS,
        "vereadores": [asdict(v) for v in sorted(vereadores, key=lambda v: v.nome)],
        "votacoes": votacoes,
        "presencas": presencas,
        "proposicoes": sorted(prop_rows, key=lambda r: (r["tipo"], -r["ano"], int(r["numero"]))),
        "stats": {
            "votacoes": {**vstats, "simbolicas_no_periodo": simbolicas, "unmatched_names": {}},
            "presenca": {"sessoes_na_arvore": sum(1 for s in sessions if int(s.data[:4]) >= args.presenca_from),
                         "sessoes_lidas": len(sessoes), "sessoes_sem_arquivo": missing,
                         "marcas": dict(Counter(r["status"] for s in sessoes for r in s.linhas)),
                         "ultima_sessao": latest.data if latest else None},
            "proposicoes": {"total": len(prop_rows), "por_tipo_ano": raw_counts,
                            "unmatched_authors": dict(unmatched_authors.most_common()), "com_outros": 0},
            "vereadores": {"em_exercicio": len(em_exercicio), "cards_membros": len(membros),
                           "com_foto": sum(1 for v in vereadores if v.foto)},
            "presenca_unmatched": [],
            "requests_made": dl.requests_made, "args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
        },
        "sources": [{"name": k, "url": f.url, "accessed_at": f.accessed_at, "checksum": f"sha256:{f.sha256}"}
                    for k, f in dl.sources.items()],
    }
    out = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1))
    log(f"wrote {out} ({out.stat().st_size/1e6:.1f} MB); {dl.requests_made} network requests")
    return 0
