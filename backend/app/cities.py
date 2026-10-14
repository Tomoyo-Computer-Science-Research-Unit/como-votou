"""The cities the project publishes (frontend/data/cities.json) and the source adapter of each.

Every Câmara publishes in its own way, so each city has its own ETL module; they all write a
snapshot of the same shape (see app/etl/export_snapshot.py for Rio, app/etl/snapshot_sp.py for
São Paulo). To add a capital: write its adapter, register it in ADAPTERS, add the city to
cities.json and its texts to frontend/lib/uf.ts.
"""
from __future__ import annotations

import json
from typing import Callable

from . import config


def load_cities() -> list[dict]:
    return json.loads((config.FRONTEND_DATA_DIR / "cities.json").read_text(encoding="utf-8"))["cities"]


def city_ufs() -> list[str]:
    return [c["uf"].upper() for c in load_cities()]


def adapter(uf: str) -> Callable:
    """run(args) -> int for the city's ETL. Rio's lives in export_snapshot itself (main path)."""
    uf = uf.upper()
    if uf == "SP":
        from .etl import snapshot_sp
        return snapshot_sp.run
    raise KeyError(f"no source adapter for {uf}; see app/cities.py")
