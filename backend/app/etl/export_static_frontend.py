"""Turn data/snapshot.json into the static files the frontend reads.

    python -m app.etl.export_static_frontend [--snapshot data/snapshot.json] [--out frontend/lib] [--fotos frontend/public/fotos]

Writes, under --out:
  static-data.generated.json             everything the list/overview pages need (no per-vereador votes);
                                         shape = types in frontend/lib/static-api.ts
  static-votacoes/<votacao>.generated.json   {votos: {vereador_id: voto}} (":" in ids becomes "-")
  static-vereadores/<cvd-N>.generated.json   {votos: [...], proposicoes: [...]} newest first
and copies the photos to --fotos (downscaled to 160 px wide).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .. import config
from .aggregates import enrich_votacoes, vereador_aggregates

EMENTA_MAX = 240
FOTO_MAX_W = 160


def log(*a: object) -> None:
    print(*a, file=sys.stderr, flush=True)


def fs_id(s: str) -> str:
    """Filesystem-safe id: 'cvd:390' -> 'cvd-390', '<unid>:0' -> '<unid>-0'."""
    return re.sub(r"[^A-Za-z0-9_-]", "-", s)


def short(s: str | None, n: int = EMENTA_MAX) -> str | None:
    if s is None:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def dump(path: Path, obj: object) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    path.write_text(data)
    return len(data.encode())


def copy_photo(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image
        with Image.open(src) as im:
            im = im.convert("RGB")
            if im.width > FOTO_MAX_W:
                im = im.resize((FOTO_MAX_W, round(im.height * FOTO_MAX_W / im.width)), Image.LANCZOS)
            im.save(dst, "JPEG", quality=82, optimize=True)
    except ImportError:
        shutil.copyfile(src, dst)


def summarize_sources(sources: list[dict]) -> list[dict]:
    kinds = [
        ("Lista de vereadores (camara.rio)", r"vereadores_atuais\.php|/vereadores/anteriores"),
        ("Frequência mensal (camara.rio)", r"frequencia-dos-vereadores"),
        ("SPL scpro.nsf (proposições 12ª)", r"/scpro\.nsf/"),
        ("SPL scpro2124.nsf (proposições 11ª)", r"/scpro2124\.nsf/"),
        ("discvot.nsf índice de sessões", r"/discvot\.nsf/[0-9a-f]{32}\?ReadViewEntries"),
        ("discvot.nsf busca full-text", r"/discvot\.nsf/[0-9a-f]{32}\?SearchView"),
        ("discvot.nsf documentos de sessão", r"/discvot\.nsf/[0-9a-f]{32}/[0-9a-f]{32}\?OpenDocument"),
    ]
    out = []
    for name, pat in kinds:
        rows = [s for s in sources if re.search(pat, s["url"], re.I)]
        if rows:
            out.append({"name": name, "url": rows[0]["url"], "accessed_at": max(r["accessed_at"] for r in rows),
                        "first_accessed_at": min(r["accessed_at"] for r in rows), "count": len(rows)})
    return out


def build(snapshot: dict) -> tuple[dict, dict[str, dict], dict[str, dict]]:
    """Return (static_data, per_votacao_files, per_vereador_files) as python objects."""
    legs = snapshot["legislatures"]
    vereadores = snapshot["vereadores"]
    votacoes = enrich_votacoes(sorted(snapshot["votacoes"], key=lambda v: (v["data"] or "", v["id"]), reverse=True), vereadores, legs)
    presencas = snapshot["presencas"]
    proposicoes = snapshot["proposicoes"]
    agg = vereador_aggregates(vereadores, votacoes, presencas, proposicoes, legs)
    vstats = snapshot["stats"]["votacoes"]

    # --- per-vereador files -------------------------------------------------------------------
    votos_by_v: dict[str, list[dict]] = defaultdict(list)
    for vt in votacoes:  # already newest first
        for vid, voto in vt["votos"].items():
            votos_by_v[vid].append({"votacao_id": vt["id"], "voto": voto})   # shape: static-api.ts VotoLinha
    props_by_v: dict[str, list[dict]] = defaultdict(list)
    for p in sorted(proposicoes, key=lambda p: (p["data"] or "", p["id"]), reverse=True):
        for vid in p.get("autores_ids", []):
            props_by_v[vid].append({"id": p["id"], "tipo": p["tipo"], "numero": p["numero"], "ano": p["ano"],
                                    "ementa": p["ementa"], "data": p["data"],
                                    "coautores": [x for x in p["autores_ids"] if x != vid],
                                    "autores_raw": p.get("autores_raw") or ", ".join(p["autores"]),
                                    "outros": bool(p.get("autores_outros"))})
    per_vereador = {v["id"]: {"id": v["id"], "votos": votos_by_v.get(v["id"], []), "proposicoes": props_by_v.get(v["id"], [])}
                    for v in vereadores}

    # --- static-data -------------------------------------------------------------------------
    vrows = []
    for v in sorted(vereadores, key=lambda v: v["nome"]):
        a = agg[v["id"]]
        vrows.append({
            "id": v["id"], "nome": v["nome"], "nome_parlamentar": v["nome_parlamentar"], "partido": v["partido"],
            "partidos_por_legislatura": v["partidos_por_legislatura"], "legislaturas": v["legislaturas"],
            "situacao": v["situacao"], "foto": ("fotos/" + Path(v["foto"]).name) if v.get("foto") else None,
            "gabinete": v.get("gabinete"), "telefone": v.get("telefone"), "email": v.get("email"),
            "perfil_url": v.get("perfil_url"),
            "presenca": a["presenca"], "votos": a["votos"], "participacao": a["participacao"],
            "com_maioria": a["com_maioria"], "contra_partido": a["contra_partido"],
            "contra_partido_taxa": a["contra_partido_taxa"], "contra_partido_base": a["contra_partido_base"],
            "proposicoes_por_tipo": a["proposicoes_por_tipo"],
            "totais": {"proposicoes": a["proposicoes_total"], "votos_cast": a["votos_cast"],
                       "votacoes_registradas": a["votacoes_registradas"]},
        })
    vt_rows = []
    per_votacao = {}
    for vt in votacoes:
        p = vt["proposicao"]
        vt_rows.append({   # shape of frontend/lib/static-api.ts `Votacao`; per-vereador votes are NOT here
            "id": vt["id"], "data": vt["data"], "hora": vt["hora"], "legislatura": vt["legislatura"], "sessao": vt["sessao"],
            "proposicao": {"id": p.get("id") or "", "tipo": p.get("tipo") or "", "numero": p.get("numero") or "",
                           "ano": p.get("ano"), "ementa": short(p.get("ementa")) or "",
                           "autores": p.get("autores", []), "autores_ids": p.get("autores_ids", [])},
            "objeto": vt.get("objeto"), "resultado": vt["resultado"], "contagem": vt["contagem"],
            "lado_vencedor": vt["lado_vencedor"], "por_partido": vt["por_partido"], "presidente": vt.get("presidente"),
            "ausentes": sum(1 for x in vt["votos"].values() if x == "ausente"), "fonte": vt["fonte"],
        })
        per_votacao[vt["id"]] = {"id": vt["id"], "data": vt["data"], "hora": vt["hora"], "sessao": vt["sessao"],
                                 "proposicao": p, "objeto": vt.get("objeto"), "resultado": vt["resultado"],
                                 "resultado_frase": vt.get("resultado_frase"), "contagem": vt["contagem"],
                                 "lado_vencedor": vt["lado_vencedor"], "por_partido": vt["por_partido"],
                                 "presidente": vt.get("presidente"), "roster_mes": vt.get("roster_mes"),
                                 "votos": vt["votos"], "fonte": vt["fonte"]}

    meses = sorted({f"{r['ano']}-{r['mes']:02d}" for r in presencas})
    prop_por_tipo: Counter = Counter(p["tipo"] for p in proposicoes)
    prop_por_ano: dict[str, Counter] = defaultdict(Counter)
    for p in proposicoes:
        prop_por_ano[str(p["ano"])][p["tipo"]] += 1
    nomes = sorted(set(vstats.get("unmatched_names", {})) | set(snapshot["stats"].get("proposicoes", {}).get("unmatched_authors", {}))
                   | set(snapshot["stats"].get("presenca_unmatched", [])))
    por_ano_vot: dict[str, Counter] = defaultdict(Counter)
    for vt in votacoes:
        por_ano_vot[vt["data"][:4]]["votacoes"] += 1
        por_ano_vot[vt["data"][:4]][f"resultado_{vt['resultado'] or 'indefinido'}"] += 1
    static = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "snapshot_generated_at": snapshot["generated_at"],
        "legislaturas": legs,
        "vereadores": vrows,
        "votacoes": vt_rows,
        "presenca_meses": meses,
        "stats": {
            "votacoes": {"candidatos": vstats.get("candidates_in_range"), "lidos": vstats.get("docs_fetched"),
                         "com_votacao": vstats.get("docs_with_roll_call"), "total": len(votacoes),
                         "sem_resultado": sum(1 for vt in votacoes if not vt["resultado"]),
                         "sem_presidente": sum(1 for vt in votacoes if not vt.get("presidente")),
                         "contagem_mismatches": vstats.get("contagem_mismatches"),
                         "impresso_discrepancies": len(vstats.get("impresso_discrepancies", [])),
                         "docs_failed": len(vstats.get("docs_failed", [])),
                         "por_ano": {y: dict(vstats.get("por_ano", {}).get(y, {}), **por_ano_vot.get(y, {}))
                                     for y in sorted(set(vstats.get("por_ano", {})) | set(por_ano_vot))}},
            "presenca": {"meses_com_dado": len(meses), "primeiro_mes": meses[0] if meses else None,
                         "ultimo_mes": meses[-1] if meses else None, "linhas": len(presencas)},
            "proposicoes": {"total": len(proposicoes), "por_tipo": dict(prop_por_tipo),
                            "por_ano": {y: dict(c) for y, c in sorted(prop_por_ano.items())},
                            "sem_autor_casado": sum(1 for p in proposicoes if not p.get("autores_ids")
                                                    and any(not _inst(a) for a in p["autores"]))},
            "nomes_nao_casados": nomes,
        },
        "sources": summarize_sources(snapshot["sources"]),
    }
    return static, per_votacao, per_vereador


def _inst(a: str) -> bool:
    from ..names import is_institutional
    return is_institutional(a)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", type=Path, default=config.SNAPSHOT_PATH)
    ap.add_argument("--out", type=Path, default=config.PROJECT_DIR / "frontend" / "lib")
    ap.add_argument("--fotos", type=Path, default=config.PROJECT_DIR / "frontend" / "public" / "fotos")
    ap.add_argument("--no-fotos", action="store_true")
    args = ap.parse_args(argv)

    snapshot = json.loads(args.snapshot.read_text())
    static, per_votacao, per_vereador = build(snapshot)

    out = args.out
    for sub in ("static-votacoes", "static-vereadores"):
        if (out / sub).exists():
            shutil.rmtree(out / sub)
    n_main = dump(out / "static-data.generated.json", static)
    n_vot = sum(dump(out / "static-votacoes" / f"{fs_id(k)}.generated.json", v) for k, v in per_votacao.items())
    n_ver = sum(dump(out / "static-vereadores" / f"{fs_id(k)}.generated.json", v) for k, v in per_vereador.items())
    log(f"static-data.generated.json: {n_main/1024:.0f} KB ({len(static['vereadores'])} vereadores, {len(static['votacoes'])} votações)")
    log(f"static-votacoes/: {len(per_votacao)} files, {n_vot/1024:.0f} KB")
    log(f"static-vereadores/: {len(per_vereador)} files, {n_ver/1024:.0f} KB")
    if not args.no_fotos:
        n = 0
        for v in snapshot["vereadores"]:
            if v.get("foto"):
                src = config.DATA_DIR / v["foto"]
                if src.exists():
                    copy_photo(src, args.fotos / src.name)
                    n += 1
        total = sum(p.stat().st_size for p in args.fotos.glob("*.jpg")) if args.fotos.exists() else 0
        log(f"fotos: {n} files, {total/1024:.0f} KB under {args.fotos}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
