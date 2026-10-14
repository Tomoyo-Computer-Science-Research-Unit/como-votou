"""Paths, identity and politeness settings shared by the ETL."""
from __future__ import annotations

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
SNAPSHOT_PATH = DATA_DIR / "snapshot.json"

USER_AGENT = "tomoyo-g0v-research (contact: g0v@tomoyo.systems)"
REQUEST_DELAY_S = 1.0
TIMEOUT_S = 120.0

# camara.rio and aplicnt.camara.rj.gov.br serve a Sectigo OV leaf without the
# intermediate; this bundle = system roots + the missing intermediate.
CA_BUNDLE = BACKEND_DIR / "app" / "cabundle.pem"

CAMARA = "https://www.camara.rio"
SPL = "https://aplicnt.camara.rj.gov.br/APL/Legislativos"
DISCVOT_VIEW = f"{SPL}/discvot.nsf/5d50d39bd976391b83256536006a2502"
