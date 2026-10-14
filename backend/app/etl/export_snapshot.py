"""Run the whole ETL and write data/snapshot.json.

    python -m app.etl.export_snapshot --all            # daily: both legislatures, no doc budget, refresh index pages
    python -m app.etl.export_snapshot --offline        # rebuild from the raw cache only (no network)
    python -m app.etl.export_snapshot [--max-docs N] [--from-year 2021] [--presenca-from 2021]
    python -m app.etl.export_snapshot --uf SP --all    # Câmara Municipal de São Paulo (app/etl/snapshot_sp.py)

Every response is cached under data/raw/. A re-run only hits the network for pages that can
change (roster, current SPL views, the newest months of the session index, the current-year
full-text search, the current and previous attendance months) and for session documents it has
never read; past attendance months are re-pulled only when --presenca-refresh-from says so.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .. import config
from ..cities import adapter, city_ufs
from ..http import Downloader
from ..names import NameResolver, has_others, is_institutional, norm, slug, split_authors
from ..parsers.discvot import MONTHS, SessaoItem, parse_item, parse_search_unids, parse_session_doc, parse_view_items
from ..parsers.presenca import parse_frequencia
from ..parsers.spl import Proposicao, entry_values, parse_proposicoes
from ..parsers.vereadores import Vereador, parse_vereadores_anteriores, parse_vereadores_atuais
from .aggregates import lado_vencedor, legislatura_of

LEGISLATURAS = [
    {"numero": 11, "inicio": "2021-01-01", "fim": "2024-12-31", "spl_db": "scpro2124.nsf"},
    {"numero": 12, "inicio": "2025-01-01", "fim": "2028-12-31", "spl_db": "scpro.nsf"},
]
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
         "Setembro", "Outubro", "Novembro", "Dezembro"]
# Views fetched per database (indicações, moções, requerimentos, ofícios are large and
# low-value for this prototype; their totals are reported in FINDINGS.md).
SPL_VIEWS = {"scpro.nsf": ["vlei", "vleicomp", "vdecreto", "vemenda", "vresolucao", "vreqinf"],
             "scpro2124.nsf": ["vlei", "vleicomp", "vdecreto", "vemenda", "vresolucao", "vreqinf"]}
# Only the current legislature's database still changes.
SPL_LIVE_DBS = {"scpro.nsf"}


def log(*a: object) -> None:
    print(*a, file=sys.stderr, flush=True)


def photo_sink_factory(photos_dir: Path):
    photos_dir.mkdir(parents=True, exist_ok=True)

    def sink(cvd: str, data_uri: str) -> str:
        m = re.match(r"data:image/(\w+);base64,(.*)", data_uri, re.S)
        if not m:
            return data_uri
        ext = "jpg" if m.group(1) in ("jpeg", "jpg") else m.group(1)
        p = photos_dir / f"{cvd}.{ext}"
        if not p.exists():
            p.write_bytes(base64.b64decode(m.group(2)))
        return f"photos/{p.name}"
    return sink


def load_vereadores(dl: Downloader, refresh: bool) -> list[Vereador]:
    cur = dl.fetch(f"{config.CAMARA}/includes_php/vereadores_atuais.php?imprimir=N", refresh=refresh)
    atuais = parse_vereadores_atuais(cur.text("latin-1"), 12, photo_sink_factory(config.DATA_DIR / "photos"))
    ant = parse_vereadores_anteriores(dl.fetch(f"{config.CAMARA}/vereadores/anteriores", refresh=refresh).text())
    by_id = {v.id: v for v in atuais}
    for v in atuais:
        v.perfil_url = f"{config.CAMARA}/includes_php/vereador.php?cvd={v.id.split(':')[1]}"
    for a in ant:
        if a.id in by_id:
            v = by_id[a.id]
            v.legislaturas = sorted(set(v.legislaturas) | set(a.legislaturas))
            v.partidos_por_legislatura = {**a.partidos_por_legislatura, **v.partidos_por_legislatura}
        elif 11 in a.legislaturas:
            a.situacao = "fora_de_exercicio"
            a.partido = a.partidos_por_legislatura.get("11")
            by_id[a.id] = a
    return list(by_id.values())


def add_attendance_roster(vereadores: list[Vereador], presencas: list[dict], resolver: NameResolver, from_year: int) -> int:
    """Attendance tables list every seat-holder of the month (suplentes included); add the missing ones."""
    added = 0
    for row in presencas:
        if row["ano"] < from_year or resolver.resolve(row["vereador_nome"], count_unmatched=False):
            continue
        nome = " ".join(w.capitalize() if len(w) > 2 else w.lower() for w in row["vereador_nome"].split())
        leg = legislatura_of(f"{row['ano']}-{row['mes']:02d}-01", LEGISLATURAS) or 12
        v = Vereador(id=f"nome:{slug(nome)}", nome=nome, nome_parlamentar=nome, partido=None,
                     legislaturas=[leg], situacao="constou_na_frequencia", foto=None)
        vereadores.append(v)
        resolver.add(v.id, nome)
        added += 1
    return added


def load_presencas(dl: Downloader, from_year: int, refresh: bool, refresh_from: tuple[int, int] | None) -> tuple[list[dict], list[dict]]:
    now = datetime.now()
    prev = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
    rows: list[dict] = []
    pages: list[dict] = []
    url = f"{config.CAMARA}/atividade-parlamentar/plenario/frequencia-dos-vereadores"
    for ano in range(from_year, now.year + 1):
        for mes in range(1, 13):
            if (ano, mes) > (now.year, now.month):
                break
            rf = refresh and ((ano, mes) in ((now.year, now.month), prev) or (refresh_from is not None and (ano, mes) >= refresh_from))
            f = dl.fetch(url, data={"ano": str(ano), "mes": f"{mes}|{MESES[mes-1]}", "sessao": "1", "submit": " Consultar "}, refresh=rf)
            page = parse_frequencia(f.text(), ano, mes)
            pages.append({"ano": ano, "mes": mes, "atualizado_em": page.atualizado_em, "linhas": len(page.linhas),
                          "observacoes": page.observacoes, "accessed_at": f.accessed_at})
            rows.extend(asdict(l) for l in page.linhas)
    return rows, pages


def read_view(dl: Downloader, db: str, view: str, refresh: bool, max_pages: int = 40) -> list[dict]:
    """Page a Domino view as JSON, 1000 entries per request."""
    docs: list[dict] = []
    start = 1
    for _ in range(max_pages):
        url = f"{config.SPL}/{db}/{view}?ReadViewEntries&OutputFormat=JSON&Start={start}&Count=1000"
        d = dl.fetch(url, refresh=refresh).json()
        entries = d.get("viewentry", [])
        docs.append(d)
        if len(entries) < 1000:
            break
        start += len(entries)
    return docs


def load_proposicoes(dl: Downloader, from_year: int, refresh: bool) -> tuple[dict[str, Proposicao], dict[str, int]]:
    out: dict[str, Proposicao] = {}
    raw_counts: dict[str, int] = {}
    for db, views in SPL_VIEWS.items():
        for view in views:
            n = 0
            try:
                pages = read_view(dl, db, view, refresh and db in SPL_LIVE_DBS)
            except FileNotFoundError as e:   # --offline and never fetched
                log(f"  {db}/{view}: skipped ({e})")
                continue
            for page in pages:
                for p in parse_proposicoes(page, view, db):
                    n += 1
                    if p.ano >= from_year and p.id not in out:
                        out[p.id] = p
            raw_counts[f"{db}/{view}"] = n
            log(f"  {db}/{view}: {n} entries")
    return out, raw_counts


def load_session_items(dl: Downloader, from_year: int, refresh_months: int = 0) -> list[SessaoItem]:
    """Walk the categorised view by position: Start=<year_idx>.<month_idx> (flat offsets > 1000 return nothing).

    The view is sorted newest first at every level, so position 1.1 is the current month;
    ``refresh_months`` newest months of the newest year are re-fetched (that is where new items appear).
    """
    items: list[SessaoItem] = []
    y = 1
    while y < 40:
        head = dl.fetch(f"{config.DISCVOT_VIEW}?ReadViewEntries&OutputFormat=JSON&ExpandView&Start={y}&Count=1",
                        refresh=(y == 1 and refresh_months > 0)).json()
        es = head.get("viewentry", [])
        if not es:
            break
        year = int(re.sub(r"\D", "", entry_values(es[0])[0]) or 0)
        if year < from_year:
            break
        for m in range(1, 13):
            pos = f"{y}.{m}"
            rf = y == 1 and m <= refresh_months
            d = dl.fetch(f"{config.DISCVOT_VIEW}?ReadViewEntries&OutputFormat=JSON&ExpandView&Start={pos}&Count=1000", refresh=rf).json()
            es = d.get("viewentry", [])
            if not es or not es[0].get("@position", "").startswith(pos):
                break
            if len(es) >= 1000:  # page this month day by day
                month_name = entry_values(es[0])[0]
                for day in range(1, 40):
                    dpos = f"{pos}.{day}"
                    dd = dl.fetch(f"{config.DISCVOT_VIEW}?ReadViewEntries&OutputFormat=JSON&ExpandView&Start={dpos}&Count=1000", refresh=rf).json()
                    des = dd.get("viewentry", [])
                    if not des or not des[0].get("@position", "").startswith(dpos):
                        break
                    dd["viewentry"] = [e for e in des if e.get("@position") == dpos or e.get("@position", "").startswith(dpos + ".")]
                    items.extend(parse_view_items(dd, {"year": str(year), "month": MONTHS.get(month_name.lower())}))
                continue
            d["viewentry"] = [e for e in es if e.get("@position") == pos or e.get("@position", "").startswith(pos + ".")]
            items.extend(parse_view_items(d, {"year": str(year)}))
        y += 1
    return [i for i in items if i.data and int(i.data[:4]) >= from_year]


def search_unids(dl: Downloader, query: str, refresh: bool = False) -> list[str]:
    unids: list[str] = []
    start = 1
    for _ in range(20):
        url = (f"{config.DISCVOT_VIEW}?SearchView&Query={query}&Count=1000&SearchMax=5000&Start={start}")
        page = parse_search_unids(dl.fetch(url, refresh=refresh).text())
        unids.extend(page)
        if len(page) < 1000:
            break
        start += len(page)
    return unids


def exercise_by_month(presencas: list[dict]) -> dict[tuple[int, int], set[str]]:
    out: dict[tuple[int, int], set[str]] = {}
    for r in presencas:
        if r.get("vereador_id"):
            out.setdefault((r["ano"], r["mes"]), set()).add(r["vereador_id"])
    return out


def roster_for_date(data: str | None, ex: dict[tuple[int, int], set[str]]) -> tuple[set[str], str | None]:
    """Vereadores in exercise on ``data``: the attendance table of that month, else the latest earlier month."""
    if not data:
        return set(), None
    y, m = int(data[:4]), int(data[5:7])
    keys = sorted(k for k in ex if k <= (y, m) and ex[k])
    if not keys:
        return set(), None
    k = keys[-1]
    return ex[k], f"{k[0]}-{k[1]:02d}"


def build_votacoes(dl: Downloader, items: list[SessaoItem], props: dict[str, Proposicao], resolver: NameResolver,
                   presencas: list[dict], from_year: int, max_docs: int, refresh: bool,
                   prop_author_ids: dict[str, list[str]] | None = None) -> tuple[list[dict], dict]:
    prop_author_ids = prop_author_ids or {}
    by_unid = {i.unid: i for i in items}
    hits: set[str] = set()
    now_year = datetime.now().year
    for y in range(from_year, now_year + 1):
        h = search_unids(dl, f"votaram%20AND%20{y}", refresh=refresh and y == now_year)
        log(f"  search 'votaram AND {y}': {len(h)} hits")
        hits.update(h)
    candidates = sorted((by_unid[u] for u in hits if u in by_unid), key=lambda i: i.data or "", reverse=True)
    por_ano: dict[str, dict[str, int]] = {}
    for c in candidates:
        por_ano.setdefault(c.data[:4], {"candidatos": 0, "lidos": 0, "com_votacao": 0, "votacoes": 0, "sem_resultado": 0})["candidatos"] += 1
    stats: dict = {"session_items_in_range": len(items),
                   "proposicao_items_in_range": sum(1 for i in items if parse_item(i.item)),
                   "search_hits": len(hits), "candidates_in_range": len(candidates), "docs_fetched": 0,
                   "docs_with_roll_call": 0, "docs_failed": [], "por_ano": por_ano, "unmatched_names": {},
                   "contagem_mismatches": 0, "impresso_discrepancies": [], "presentes_votando_discrepancies": 0, "sem_presidente": 0,
                   "roster_fallback_month": 0, "voters_without_roster": {}}
    ex = exercise_by_month(presencas)

    votacoes: list[dict] = []
    todo = candidates if max_docs <= 0 else candidates[:max_docs]
    for it in todo:
        url = f"{config.DISCVOT_VIEW}/{it.unid.lower()}?OpenDocument"
        try:
            doc = parse_session_doc(dl.fetch(url).text())
        except Exception as e:  # keep going; the daily run will retry what is missing
            log(f"  FAILED {it.data} {it.unid}: {e!r}")
            stats["docs_failed"].append({"unid": it.unid, "data": it.data, "error": repr(e)[:200]})
            continue
        stats["docs_fetched"] += 1
        pa = por_ano[it.data[:4]]
        pa["lidos"] += 1
        if not doc.votacoes:
            continue
        stats["docs_with_roll_call"] += 1
        pa["com_votacao"] += 1
        parsed = parse_item(it.item) or parse_item(doc.item)
        prop: dict = {"id": None, "tipo": None, "numero": None, "ano": None, "ementa": None, "autores": [], "autores_ids": []}
        if parsed:
            tipo, numero, ano = parsed
            pid = f"{tipo}-{numero}/{ano}"
            base = props.get(pid) or props.get(f"{tipo}-{numero.split('-')[0]}/{ano}")
            prop = {"id": pid, "tipo": tipo, "numero": numero, "ano": ano,
                    "ementa": base.ementa if base else None, "autores": list(base.autores) if base else [],
                    "autores_ids": list(prop_author_ids.get(base.id, [])) if base else []}
        if not prop.get("ementa"):
            m = re.search(r'DE AUTORIA D[OAE]S? (.+?), QUE\s*"(.+?)"', doc.texto, re.S)
            if m:
                prop["autores"] = prop["autores"] or split_authors(re.sub(r"\s+", " ", m.group(1)))
                prop["ementa"] = re.sub(r"\s+", " ", m.group(2)).strip()
        if prop["autores"] and not prop["autores_ids"]:
            prop["autores_ids"] = resolve_authors(prop["autores"], resolver)[0]
        data = doc.data or it.data
        roster, roster_month = roster_for_date(data, ex)
        if roster_month and roster_month != data[:7]:
            stats["roster_fallback_month"] += 1
        def ids_for(name: str) -> list[str]:
            ids = resolver.resolve(name)
            if ids:
                return ids
            fid = f"nome:{slug(name)}"      # voter with no roster entry at all (suplente not listed anywhere)
            stats["voters_without_roster"].setdefault(fid, {"nome": name, "votos": 0, "primeira": data, "ultima": data})
            w = stats["voters_without_roster"][fid]
            w["votos"] += 1
            w["primeira"], w["ultima"] = min(w["primeira"], data), max(w["ultima"], data)
            return [fid]

        for k, rc in enumerate(doc.votacoes):
            votos: dict[str, str] = {}
            for name in rc.sim:
                for vid in ids_for(name):
                    votos[vid] = "sim"
            for name in rc.nao:
                for vid in ids_for(name):
                    votos[vid] = "nao"
            for name in rc.abstencao:
                for vid in ids_for(name):
                    votos[vid] = "abstencao"
            # contagem = resolved voters per side; checked against the counts printed in the transcript
            contagem = {"sim": sum(1 for v in votos.values() if v == "sim"),
                        "nao": sum(1 for v in votos.values() if v == "nao"),
                        "abstencao": sum(1 for v in votos.values() if v == "abstencao"),
                        "presentes_votando": rc.presentes_votando}
            if (len(set(votos.values()) - {"sim", "nao", "abstencao"}) or
                    sum(contagem[s] for s in ("sim", "nao", "abstencao")) != len(votos)):
                stats["contagem_mismatches"] += 1          # cannot happen by construction; kept as an invariant
            for side in ("sim", "nao", "abstencao"):
                printed = rc.impresso.get(side)
                if printed is not None and printed != contagem[side]:
                    stats["impresso_discrepancies"].append(
                        {"id": f"{it.unid.lower()}:{k}", "data": it.data, "item": it.item, "lado": side,
                         "impresso": printed, "nomes": contagem[side]})
            if rc.presentes_votando is not None and rc.presentes_votando != len(rc.sim) + len(rc.nao) + len(rc.abstencao):
                stats["presentes_votando_discrepancies"] += 1
            pres_ids = resolver.resolve(rc.presidente) if rc.presidente else []
            presidente = pres_ids[0] if len(pres_ids) == 1 else None
            if presidente is None:
                stats["sem_presidente"] += 1
            elif presidente not in votos:
                votos[presidente] = "presidindo"
            for cid in roster:
                votos.setdefault(cid, "ausente")
            if rc.resultado is None:
                pa["sem_resultado"] += 1
            pa["votacoes"] += 1
            votacoes.append({
                "id": f"{it.unid.lower()}:{k}", "data": data, "hora": doc.hora,
                "legislatura": legislatura_of(data, LEGISLATURAS),
                "sessao": {"tipo": it.sessao_tipo, "numero": it.num_sessao, "fase": it.fase},
                "proposicao": prop, "objeto": rc.objeto, "resultado": rc.resultado, "resultado_frase": rc.resultado_frase,
                "lado_vencedor": lado_vencedor(contagem),
                "contagem": contagem, "presidente": presidente, "presidente_nome": rc.presidente,
                "roster_mes": roster_month,
                "votos": votos,
                "fonte": url,
            })
    stats["unmatched_names"] = dict(sorted(resolver.unmatched.items(), key=lambda kv: -kv[1]))
    return votacoes, stats


def resolve_authors(autores: list[str], resolver: NameResolver) -> tuple[list[str], bool]:
    ids: list[str] = []
    outros = False
    for a in autores:
        outros = outros or has_others(a)
        for part in split_authors(a):
            if is_institutional(part):
                continue
            for vid in resolver.resolve(part):
                if vid not in ids:
                    ids.append(vid)
    return ids, outros


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uf", choices=city_ufs(), default="RJ", type=str.upper, help="city (frontend/data/cities.json); RJ by default")
    ap.add_argument("--all", action="store_true", help="daily mode: --from-year 2021 --presenca-from 2021 --max-docs 0")
    ap.add_argument("--max-docs", type=int, default=600, help="max discvot session documents to read (0 = no limit)")
    ap.add_argument("--from-year", type=int, default=2025, help="first year for votações/proposições")
    ap.add_argument("--presenca-from", type=int, default=2021)
    ap.add_argument("--presenca-refresh-from", type=str, default=None, metavar="YYYY-MM",
                    help="also re-pull attendance months from this one on (abonos change retroactively)")
    ap.add_argument("--offline", action="store_true", help="never touch the network; rebuild from data/raw only")
    ap.add_argument("--no-refresh", action="store_true", help="do not re-fetch index pages (roster, SPL views, newest months)")
    ap.add_argument("--out", type=Path, default=None, help="default: data/snapshot.json (RJ), data/sp/snapshot.json (SP)")
    args = ap.parse_args(argv)
    if args.all:
        args.from_year, args.presenca_from, args.max_docs = 2021, 2021, 0
    if args.out is None:
        args.out = config.snapshot_path(args.uf)
    if args.uf != "RJ":      # every other city has its own source adapter (app/cities.py)
        if args.presenca_refresh_from and len(args.presenca_refresh_from) == 7:
            args.presenca_refresh_from += "-01"
        return adapter(args.uf)(args)
    refresh = not (args.offline or args.no_refresh)
    refresh_from = None
    if args.presenca_refresh_from:
        y, m = args.presenca_refresh_from.split("-")
        refresh_from = (int(y), int(m))

    dl = Downloader(offline=args.offline)
    log("vereadores ...")
    vereadores = load_vereadores(dl, refresh)
    log(f"  {len(vereadores)} vereadores")
    resolver = NameResolver(vereadores)
    log("presenças ...")
    presencas, presenca_pages = load_presencas(dl, args.presenca_from, refresh, refresh_from)
    log(f"  {len(presencas)} rows / {len(presenca_pages)} months")
    log(f"  {add_attendance_roster(vereadores, presencas, resolver, args.from_year)} vereadores added from attendance tables")
    for r in presencas:
        ids = resolver.resolve(r["vereador_nome"])
        r["vereador_id"] = ids[0] if len(ids) == 1 else None
    log("proposições ...")
    props, raw_counts = load_proposicoes(dl, args.from_year, refresh)
    log(f"  {len(props)} proposições kept (ano >= {args.from_year})")
    prop_rows: list[dict] = []
    author_resolver = NameResolver(vereadores)
    for p in sorted(props.values(), key=lambda p: (p.tipo, -p.ano, p.numero)):
        d = asdict(p)
        d["autores_ids"], d["autores_outros"] = resolve_authors(p.autores, author_resolver)
        prop_rows.append(d)
    prop_author_ids = {r["id"]: r["autores_ids"] for r in prop_rows}
    log("sessões / votações ...")
    items = load_session_items(dl, args.from_year, refresh_months=2 if refresh else 0)
    votacoes, vstats = build_votacoes(dl, items, props, resolver, presencas, args.from_year, args.max_docs, refresh, prop_author_ids)
    log(f"  {len(votacoes)} votações nominais; stats {json.dumps({k: v for k, v in vstats.items() if k not in ('docs_failed', 'impresso_discrepancies')}, ensure_ascii=False)}")
    log(f"  {len(vstats['impresso_discrepancies'])} printed-count discrepancies")
    # Voters that no roster page or attendance table lists: give them a row so the frontend can show them.
    # A name seen in fewer than 3 roll calls is more likely a parsing artefact than a person; it stays nome:-only.
    for fid, w in vstats["voters_without_roster"].items():
        if w["votos"] >= 3 and not any(v.id == fid for v in vereadores):
            nome = re.sub(r"\s+", " ", w["nome"]).strip()
            vereadores.append(Vereador(id=fid, nome=nome, nome_parlamentar=nome, partido=None,
                                       legislaturas=[legislatura_of(w["primeira"], LEGISLATURAS) or 12],
                                       situacao="constou_em_votacao", foto=None))
    author_unmatched = dict(sorted(author_resolver.unmatched.items(), key=lambda kv: -kv[1]))
    presenca_unmatched = sorted({r["vereador_nome"] for r in presencas if not r.get("vereador_id")})

    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "legislatures": LEGISLATURAS,
        "vereadores": [asdict(v) for v in sorted(vereadores, key=lambda v: v.nome)],
        "votacoes": votacoes,
        "presencas": presencas,
        "proposicoes": prop_rows,
        "stats": {"presenca_pages": presenca_pages, "spl_view_entries": raw_counts, "votacoes": vstats,
                  "proposicoes": {"total": len(prop_rows), "unmatched_authors": author_unmatched,
                                  "com_outros": sum(1 for r in prop_rows if r["autores_outros"])},
                  "presenca_unmatched": presenca_unmatched,
                  "requests_made": dl.requests_made, "args": vars(args) | {"out": str(args.out)}},
        "sources": [{"name": k, "url": f.url, "accessed_at": f.accessed_at, "checksum": f"sha256:{f.sha256}"}
                    for k, f in dl.sources.items()],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1))
    log(f"wrote {args.out} ({args.out.stat().st_size/1e6:.1f} MB); {dl.requests_made} network requests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
