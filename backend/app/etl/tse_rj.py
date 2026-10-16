"""Vereadores eleitos nos 92 municípios do Estado do Rio de Janeiro, 2020 e 2024, pelo TSE.

Fontes (Portal de Dados Abertos do TSE, arquivos nacionais com um CSV por UF dentro do zip):
  consulta_cand_<ano>.zip              candidatos: nome, nome de urna, partido, número, título eleitoral
  votacao_candidato_munzona_<ano>.zip  votos nominais por zona e situação final (eleito, suplente)
  foto_cand<ano>_RJ_div.zip            fotos, lidas do zip remoto por faixa de bytes (só as que usamos)

Os zips são grandes (50 a 85 MB; o de fotos, 500 a 750 MB) e mudam pouco. Ficam em
data/raw/tse/ e só são baixados de novo quando o Last-Modified do TSE muda e a cópia tem mais de
TSE_MAX_AGE_DAYS dias (o TSE regera os arquivos de 2024 quase todo dia, com mudanças mínimas).

Saída: data/rjm/tse.json e data/rjm/photos/<slug>/<id>.jpg.

    python -m app.etl.tse_rj            # baixa o que faltar e regera tse.json
    python -m app.etl.tse_rj --no-photos
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .. import config

CDN = "https://cdn.tse.jus.br/estatistica/sead"
YEARS = (2020, 2024)
TSE_DIR = config.RAW_DIR / "tse"
OUT_DIR = config.DATA_DIR / "rjm"
IBGE_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/33/municipios"
MAX_AGE_DAYS = float(os.environ.get("TSE_MAX_AGE_DAYS", "7"))
SUPLENTES_POR_LEGENDA = 5   # suplentes guardados por partido ou federação, em ordem de votos
CARGO_VEREADOR = "13"
ELEICAO_ORDINARIA = "2"


def log(*a: object) -> None:
    print("[tse]", *a, file=sys.stderr, flush=True)


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


_LOWER = {"de", "da", "do", "das", "dos", "e", "di", "du"}


def title_name(s: str) -> str:
    """'PR JOSIAS DA CRUZ' -> 'Pr Josias da Cruz'; siglas curtas sem vogal ficam em maiúsculas."""
    words = []
    for i, w in enumerate(s.strip().lower().split()):
        if i and w in _LOWER:
            words.append(w)
        elif len(w) <= 3 and not re.search(r"[aeiouáéíóúâêôãõ]", w):
            words.append(w.upper())
        else:
            words.append("-".join(p[:1].upper() + p[1:] for p in w.split("-")))
    return " ".join(words)


# --- Downloads ------------------------------------------------------------------------------------

def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": config.USER_AGENT}, timeout=config.TIMEOUT_S, follow_redirects=True)


def ensure_zip(url: str, client: httpx.Client) -> Path:
    """Baixa o zip para data/raw/tse/ se não existe, ou se o TSE o atualizou e a cópia é velha."""
    TSE_DIR.mkdir(parents=True, exist_ok=True)
    path = TSE_DIR / url.rsplit("/", 1)[1]
    meta_path = path.with_suffix(".meta.json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    if path.exists():
        age_days = (time.time() - path.stat().st_mtime) / 86400
        if age_days < MAX_AGE_DAYS:
            return path
        head = client.head(url)
        same = head.headers.get("last-modified") == meta.get("last_modified") if meta else \
            head.headers.get("content-length") == str(path.stat().st_size)
        if head.status_code == 200 and same:
            if not meta:
                meta_path.write_text(json.dumps({"url": url, "last_modified": head.headers.get("last-modified"),
                                                 "bytes": path.stat().st_size}, indent=1))
            path.touch()
            return path
    log("baixando", url)
    tmp = path.with_suffix(".part")
    with client.stream("GET", url) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
        lm = r.headers.get("last-modified")
    tmp.replace(path)
    meta_path.write_text(json.dumps({"url": url, "last_modified": lm, "accessed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                     "bytes": path.stat().st_size}, indent=1))
    return path


def read_uf_csv(zip_path: Path, member_suffix: str) -> list[dict[str, str]]:
    with zipfile.ZipFile(zip_path) as z:
        name = next(n for n in z.namelist() if n.endswith(member_suffix))
        text = z.read(name).decode("latin-1")
    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


class RangeFile(io.RawIOBase):
    """Arquivo remoto lido por faixas de bytes, para abrir um zip de 700 MB sem baixá-lo."""

    def __init__(self, url: str, client: httpx.Client, block: int = 96 * 1024, delay_s: float = 0.25) -> None:
        self.url, self.client, self.block, self.delay_s = url, client, block, delay_s
        self.size = int(client.head(url).headers["content-length"])
        self.pos = 0
        self.requests = 0
        self._buf_start, self._buf = -1, b""
        self._last = 0.0

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset
        return self.pos

    def tell(self) -> int:
        return self.pos

    def _get(self, start: int, end: int) -> bytes:
        wait = self.delay_s - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        self.requests += 1
        r = self.client.get(self.url, headers={"Range": f"bytes={start}-{end - 1}"})
        r.raise_for_status()
        return r.content

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = self.size - self.pos
        end = min(self.pos + n, self.size)
        if end <= self.pos:
            return b""
        if not (self._buf_start <= self.pos and end <= self._buf_start + len(self._buf)):
            want_end = max(end, min(self.pos + self.block, self.size))
            self._buf_start, self._buf = self.pos, self._get(self.pos, want_end)
        out = self._buf[self.pos - self._buf_start:end - self._buf_start]
        self.pos += len(out)
        return out

    def readinto(self, b) -> int:  # type: ignore[override]
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)


# --- Parse ----------------------------------------------------------------------------------------

def person_id(titulo: str, fallback: str) -> str:
    key = titulo if titulo and titulo.strip("-0") and not titulo.startswith("#") else fallback
    return "tse:" + hashlib.sha1(key.encode()).hexdigest()[:12]


def situacao(ds: str) -> str:
    ds = ds.upper()
    if ds.startswith("ELEITO"):
        return "eleito"
    if ds == "SUPLENTE":
        return "suplente"
    return "nao_eleito"


def parse_year(year: int, client: httpx.Client) -> dict[str, dict]:
    """{tse_code: {nome, candidatos: {sq: {...}}}} só com vereadores da eleição ordinária."""
    cand_zip = ensure_zip(f"{CDN}/odsele/consulta_cand/consulta_cand_{year}.zip", client)
    vot_zip = ensure_zip(f"{CDN}/odsele/votacao_candidato_munzona/votacao_candidato_munzona_{year}.zip", client)
    cands = {r["SQ_CANDIDATO"]: r for r in read_uf_csv(cand_zip, f"_{year}_RJ.csv")
             if r["CD_CARGO"] == CARGO_VEREADOR and r["CD_TIPO_ELEICAO"] == ELEICAO_ORDINARIA}
    out: dict[str, dict] = {}
    votos: dict[str, int] = {}
    sit: dict[str, str] = {}
    for r in read_uf_csv(vot_zip, f"_{year}_RJ.csv"):
        if r["CD_CARGO"] != CARGO_VEREADOR or r["CD_TIPO_ELEICAO"] != ELEICAO_ORDINARIA:
            continue
        sq = r["SQ_CANDIDATO"]
        v = r.get("QT_VOTOS_NOMINAIS_VALIDOS") or r.get("QT_VOTOS_NOMINAIS") or "0"
        votos[sq] = votos.get(sq, 0) + max(0, int(v))
        sit[sq] = r["DS_SIT_TOT_TURNO"]
    for sq, c in cands.items():
        code = c["SG_UE"]
        m = out.setdefault(code, {"nome": c["NM_UE"], "candidatos": {}})
        fed = c.get("SG_FEDERACAO", "#NULO")
        m["candidatos"][sq] = {
            "sq": sq,
            "nome": c["NM_CANDIDATO"],
            "urna": c["NM_URNA_CANDIDATO"],
            "partido": c["SG_PARTIDO"],
            "legenda": fed if fed and not fed.startswith("#") else c["SG_PARTIDO"],
            "numero": c["NR_CANDIDATO"],
            "titulo": c.get("NR_TITULO_ELEITORAL_CANDIDATO", ""),
            "votos": votos.get(sq, 0),
            "situacao": situacao(sit.get(sq, c["DS_SIT_TOT_TURNO"])),
            "genero": c.get("DS_GENERO", ""),
        }
    return out


def build(client: httpx.Client) -> dict:
    ibge = client.get(IBGE_URL).json()
    by_slug = {slugify(m["nome"]): m for m in ibge}
    municipios: dict[str, dict] = {}
    for year in YEARS:
        for code, m in parse_year(year, client).items():
            slug = slugify(m["nome"])
            if slug not in by_slug:
                raise SystemExit(f"município do TSE sem par no IBGE: {m['nome']} ({code})")
            mun = municipios.setdefault(slug, {"slug": slug, "nome": by_slug[slug]["nome"], "ibge": by_slug[slug]["id"],
                                               "tse": code, "eleicoes": {}, "pessoas": {}})
            cands = list(m["candidatos"].values())
            eleitos = [c for c in cands if c["situacao"] == "eleito"]
            # suplentes: os N mais votados de cada legenda que elegeu alguém
            sup_keep: set[str] = set()
            by_leg: dict[str, list[dict]] = {}
            for c in cands:
                if c["situacao"] == "suplente":
                    by_leg.setdefault(c["legenda"], []).append(c)
            for rows in by_leg.values():
                rows.sort(key=lambda c: -c["votos"])
                sup_keep.update(c["sq"] for c in rows[:SUPLENTES_POR_LEGENDA])
            mun["eleicoes"][str(year)] = {
                "cadeiras": len(eleitos),
                "candidatos": len(cands),
                "votos_nominais": sum(c["votos"] for c in cands),
            }
            for c in cands:
                if c["situacao"] != "eleito" and c["sq"] not in sup_keep:
                    continue
                pid = person_id(c["titulo"], f"{year}:{c['sq']}")
                p = mun["pessoas"].setdefault(pid, {"id": pid, "eleicoes": {}})
                p["nome"] = title_name(c["nome"])
                p["urna"] = title_name(c["urna"])
                p["eleicoes"][str(year)] = {k: c[k] for k in ("sq", "partido", "numero", "votos", "situacao")}
    for mun in municipios.values():
        mun["pessoas"] = sorted(mun["pessoas"].values(), key=lambda p: p["urna"])
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "fontes": [f"{CDN}/odsele/consulta_cand/consulta_cand_{y}.zip" for y in YEARS]
                      + [f"{CDN}/odsele/votacao_candidato_munzona/votacao_candidato_munzona_{y}.zip" for y in YEARS],
            "municipios": dict(sorted(municipios.items()))}


def fetch_photos(data: dict, client: httpx.Client, skip: set[str]) -> int:
    """Fotos dos eleitos e suplentes guardados, do zip de fotos do TSE (eleição mais recente do candidato)."""
    from PIL import Image

    got = 0
    for year in sorted(YEARS, reverse=True):
        wanted: dict[str, Path] = {}
        for slug, mun in data["municipios"].items():
            if slug in skip:
                continue
            for p in mun["pessoas"]:
                e = p["eleicoes"].get(str(year))
                dst = OUT_DIR / "photos" / slug / f"{p['id'].split(':')[1]}.jpg"
                if e and not dst.exists() and not (dst.with_suffix(".none")).exists():
                    if year == max(int(y) for y in p["eleicoes"]):
                        wanted[e["sq"]] = dst
        if not wanted:
            continue
        url = f"{CDN}/eleicoes/eleicoes{year}/fotos/foto_cand{year}_RJ_div.zip"
        rf = RangeFile(url, client)
        z = zipfile.ZipFile(io.BufferedReader(rf, buffer_size=64 * 1024))
        names = {}
        for info in z.infolist():
            m = re.search(r"(\d{9,})", info.filename)
            if m:
                names[m.group(1)] = info
        log(f"fotos {year}: {len(wanted)} pedidas, {len(names)} no zip")
        for i, (sq, dst) in enumerate(sorted(wanted.items(), key=lambda kv: names[kv[0]].header_offset if kv[0] in names else 0)):
            dst.parent.mkdir(parents=True, exist_ok=True)
            info = names.get(sq)
            if info is None:
                dst.with_suffix(".none").write_text("")
                continue
            raw = z.read(info)
            try:
                im = Image.open(io.BytesIO(raw)).convert("RGB")
                im.thumbnail((160, 214))
                im.save(dst, "JPEG", quality=82, optimize=True)
                got += 1
            except Exception as exc:  # foto corrompida no TSE
                log("foto ilegível", sq, exc)
                dst.with_suffix(".none").write_text("")
            if i % 200 == 0:
                log(f"  {i}/{len(wanted)} ({rf.requests} requisições)")
    return got


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-photos", action="store_true")
    args = ap.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with _client() as client:
        data = build(client)
        n = len(data["municipios"])
        eleitos = sum(1 for m in data["municipios"].values() for p in m["pessoas"] if p["eleicoes"].get("2024", {}).get("situacao") == "eleito")
        log(f"{n} municípios, {eleitos} eleitos em 2024")
        (OUT_DIR / "tse.json").write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
        if not args.no_photos:
            log("fotos novas:", fetch_photos(data, client, skip={"rio-de-janeiro"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
