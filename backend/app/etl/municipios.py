"""Os 92 municípios do Estado do Rio: arquivos do frontend a partir do TSE e, onde houver, do SAPL.

Entradas:
  data/rjm/tse.json                 vereadores eleitos e suplentes de 2020 e 2024 (app.etl.tse_rj)
  data/rjm/photos/<slug>/*.jpg      fotos do TSE
  backend/data/rj-camaras.csv       levantamento das câmaras: site, sistema (app.etl.survey_camaras)
  data/rjm/sapl/<slug>.json         tabelas do SAPL 3 da câmara, quando há (app.etl.sapl)

Saída, por município (a capital fica de fora: tem ETL próprio e mora na raiz do site):
  frontend/data/rjm/<slug>/static-data.generated.json, static-votacoes/, static-vereadores/, fotos/
e o índice frontend/data/rj-municipios.json (nome, nível de dado, sistema, site da câmara).

Nível de dado: 0 = só vereadores (TSE); 1 = proposições; 2 = presença; 3 = votos nominais.

    python -m app.etl.municipios [--only niteroi,petropolis]
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from .. import config
from .export_static_frontend import build, copy_photo, dump, fs_id

RJM_DIR = config.DATA_DIR / "rjm"
SURVEY_CSV = config.BACKEND_DIR / "data" / "rj-camaras.csv"
OUT_DIR = config.FRONTEND_DATA_DIR / "rjm"
INDEX_PATH = config.FRONTEND_DATA_DIR / "rj-municipios.json"
CAPITAL = "rio-de-janeiro"
TSE_LEGS = [{"numero": 2021, "inicio": "2021-01-01", "fim": "2024-12-31"},
            {"numero": 2025, "inicio": "2025-01-01", "fim": "2028-12-31"}]
TSE_SOURCES = [
    {"name": "Candidatos 2020 e 2024 (TSE, consulta_cand)", "url": "https://dadosabertos.tse.jus.br/dataset/candidatos-2024"},
    {"name": "Votação nominal por município e zona (TSE)", "url": "https://dadosabertos.tse.jus.br/dataset/resultados-2024"},
]


def log(*a: object) -> None:
    print("[municipios]", *a, file=sys.stderr, flush=True)


def load_survey() -> dict[str, dict]:
    if not SURVEY_CSV.exists():
        return {}
    with SURVEY_CSV.open(encoding="utf-8") as f:
        return {r["slug"]: r for r in csv.DictReader(f)}


def situacao_tse(eleicoes: dict) -> str:
    last = max(eleicoes)
    return f"{eleicoes[last]['situacao']}_{last}"


def tse_vereador(p: dict, slug: str) -> dict:
    last = max(p["eleicoes"])
    partidos = {str(int(y) + 1): e["partido"] for y, e in p["eleicoes"].items()}
    return {
        "id": p["id"], "nome": p["nome"], "nome_parlamentar": p["urna"], "partido": p["eleicoes"][last]["partido"],
        "partidos_por_legislatura": partidos, "legislaturas": [], "situacao": situacao_tse(p["eleicoes"]),
        "foto": None, "eleicoes": p["eleicoes"],
        "_foto_src": RJM_DIR / "photos" / slug / f"{p['id'].split(':')[1]}.jpg",
    }


def nivel_of(snapshot: dict) -> int:
    if any(vt["votos"] for vt in snapshot["votacoes"]):
        return 3
    if snapshot["presencas"]:
        return 2
    if snapshot["proposicoes"]:
        return 1
    return 0


def municipio_snapshot(mun: dict, survey: dict | None) -> dict:
    vereadores = [tse_vereador(p, mun["slug"]) for p in mun["pessoas"]]
    snap = {
        "uf": "RJM", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "legislatures": TSE_LEGS, "vereadores": vereadores, "votacoes": [], "presencas": [], "proposicoes": [],
        "stats": {"votacoes": {}}, "sources": [dict(s) for s in TSE_SOURCES],
    }
    sapl_path = RJM_DIR / "sapl" / f"{mun['slug']}.json"
    if sapl_path.exists():
        from .sapl import merge_into
        merge_into(snap, json.loads(sapl_path.read_text(encoding="utf-8")))
    return snap


def export_one(mun: dict, survey: dict | None) -> dict:
    slug = mun["slug"]
    snap = municipio_snapshot(mun, survey)
    static, per_votacao, per_vereador = build(snap)
    nivel = nivel_of(snap)
    by_id = {v["id"]: v for v in snap["vereadores"]}
    out = OUT_DIR / slug
    if out.exists():
        shutil.rmtree(out)
    fotos = 0
    for row in static["vereadores"]:
        v = by_id[row["id"]]
        row["eleicoes"] = v.get("eleicoes") or {}
        if v.get("sapl_id"):
            row["sapl_id"] = v["sapl_id"]
        src = v.get("_foto_src")
        # foto de quem foi eleito ao menos uma vez ou está em exercício; suplentes ficam com as iniciais
        eleito = any(e["situacao"] == "eleito" for e in row["eleicoes"].values()) or row["situacao"] == "em_exercicio"
        if src and eleito and src.exists():
            copy_photo(src, out / "fotos" / src.name)
            row["foto"] = f"fotos/{src.name}"
            fotos += 1
    static["municipio"] = {"slug": slug, "nome": mun["nome"], "ibge": mun["ibge"], "nivel": nivel,
                           "sistema": (survey or {}).get("sistema") or "desconhecido",
                           "url_camara": (survey or {}).get("url_camara") or None,
                           "sapl_url": (survey or {}).get("sapl_url") or None}
    static["eleicoes"] = mun["eleicoes"]
    static["sources"] = snap["sources"]
    static["stats"] = {k: v for k, v in static["stats"].items() if k != "nomes_nao_casados"}
    static["stats"]["nomes_nao_casados"] = snap["stats"].get("nomes_nao_casados", [])
    dump(out / "static-data.generated.json", static)
    for k, v in per_votacao.items():
        dump(out / "static-votacoes" / f"{fs_id(k)}.generated.json", v)
    for k, v in per_vereador.items():
        if nivel >= 1:   # nível 0 não abre a ficha de votos e proposições
            dump(out / "static-vereadores" / f"{fs_id(k)}.generated.json", v)
    e24 = mun["eleicoes"].get("2024", {})
    ultima = max((vt["data"] for vt in snap["votacoes"] if vt.get("data")), default=None)
    return {"slug": slug, "nome": mun["nome"], "ibge": mun["ibge"], "nivel": nivel,
            "sistema": static["municipio"]["sistema"], "url_camara": static["municipio"]["url_camara"],
            "cadeiras": e24.get("cadeiras"), "votacoes": len(snap["votacoes"]), "presencas": len(snap["presencas"]),
            "proposicoes": len(snap["proposicoes"]), "ultima_votacao": ultima, "fotos": fotos}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="slugs separados por vírgula; o índice é atualizado só para eles")
    args = ap.parse_args(argv)
    tse = json.loads((RJM_DIR / "tse.json").read_text(encoding="utf-8"))
    survey = load_survey()
    only = {s for s in args.only.split(",") if s}
    index = {}
    if only and INDEX_PATH.exists():
        index = {m["slug"]: m for m in json.loads(INDEX_PATH.read_text(encoding="utf-8"))["municipios"]}
    for slug, mun in tse["municipios"].items():
        if slug == CAPITAL:
            s = survey.get(slug, {})
            index[slug] = {"slug": slug, "nome": mun["nome"], "ibge": mun["ibge"], "nivel": 3, "sistema": s.get("sistema") or "proprio",
                           "url_camara": s.get("url_camara") or "https://www.camara.rio", "cadeiras": mun["eleicoes"]["2024"]["cadeiras"],
                           "capital": True}
            continue
        if only and slug not in only:
            continue
        index[slug] = export_one(mun, survey.get(slug))
        log(slug, "nível", index[slug]["nivel"])
    rows = sorted(index.values(), key=lambda m: m["slug"])
    INDEX_PATH.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                      "municipios": rows}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    niveis = {n: sum(1 for m in rows if m["nivel"] == n) for n in range(4)}
    log(f"{len(rows)} municípios; por nível {niveis}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
