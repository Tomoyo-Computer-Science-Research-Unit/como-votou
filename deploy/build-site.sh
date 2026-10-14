#!/usr/bin/env bash
# Roda no droplet, por cron, uma vez por dia: puxa main e, para cada cidade de
# frontend/data/cities.json, relê o que muda na Câmara e regenera os dados. Se o código ou os dados
# mudaram desde o último build, constrói todas as cidades: a cidade raiz (Rio) em
# /root/g0v/site/vereadores e cada uma das demais em /root/g0v/site/vereadores/<slug>. A falha do
# ETL de uma cidade não derruba as outras: ela segue com os dados commitados em main.
# Falhas avisam por e-mail.
#
#   /root/g0v/build-vereadores.sh               # só reconstrói se algo mudou
#   FORCE=1 /root/g0v/build-vereadores.sh       # reconstrói de qualquer jeito
#   SKIP_DATA=1 /root/g0v/build-vereadores.sh   # não lê a Câmara; usa os dados commitados
set -euo pipefail
export PATH=/usr/local/bin:/usr/bin:/bin

REPO="${REPO:-https://github.com/Tomoyo-Computer-Science-Research-Unit/como-votou.git}"
DIR="${DIR:-/root/g0v}"
SRC="$DIR/src-vereadores"
MARK="$DIR/.vereadores-built"
RUNS="$DIR/runs-vereadores.jsonl"
BASE_PATH="/vereadores"
ALERT_TO="${ALERT_TO:-arete@tomoyo.systems}"
export NEXT_TELEMETRY_DISABLED=1
export NODE_OPTIONS="--max-old-space-size=2048"

started="$(date +%s)"
key=""
note=""

log() { echo "$(date -Is) $*"; }

record() {
  python3 - "$1" "${2:-}" "$key" "$(( $(date +%s) - started ))" >> "$RUNS" <<'PY'
import datetime, json, sys
print(json.dumps({
    "at": datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds"),
    "result": sys.argv[1], "detail": sys.argv[2] or None, "key": sys.argv[3] or None, "duration_s": int(sys.argv[4]),
}, ensure_ascii=False))
PY
}

notify() {
  printf 'From: g0v <g0v@tomoyo.systems>\nTo: %s\nSubject: %s\nContent-Type: text/plain; charset=utf-8\n\n%s\n' "$ALERT_TO" "$1" "$2" \
    | docker exec -i mailserver sendmail -t || log "aviso por e-mail falhou"
}

on_error() {
  log "falhou na linha $1"
  record "falhou" "linha $1"
  notify "[como-votou] rodada falhou" "O build-vereadores.sh parou na linha $1 em $(hostname). Veja $DIR/build-vereadores.log."
}
trap 'on_error $LINENO' ERR

[ -d "$SRC/.git" ] || git clone -q "$REPO" "$SRC"
git -C "$SRC" fetch -q origin main
git -C "$SRC" reset -q --hard origin/main
rev="$(git -C "$SRC" rev-parse --short HEAD)"

if [ -f "$SRC/deploy/build-site.sh" ] && ! cmp -s "$SRC/deploy/build-site.sh" "$0"; then
  cp "$SRC/deploy/build-site.sh" "$0"
  chmod 755 "$0"
  log "script atualizado a partir de $rev; recomeçando"
  exec "$0" "$@"
fi

PY="$SRC/backend/.venv/bin/python"
[ -x "$PY" ] || uv venv -q --python 3.12 "$SRC/backend/.venv"
uv pip install -q --python "$PY" -e "$SRC/backend"

run_etl() {   # $1 = sigla da cidade (cities.json)
  local uf="$1" lower etl_output
  lower="$(echo "$uf" | tr 'A-Z' 'a-z')"
  if etl_output="$(cd "$SRC/backend" && "$PY" -m app.etl.export_snapshot --uf "$uf" --all 2>&1 && "$PY" -m app.etl.export_static_frontend --uf "$uf" 2>&1)"; then
    log "ETL $uf ok"
  else
    log "ETL $uf falhou; usando os arquivos commitados em main"
    note="${note:+$note; }ETL $uf falhou"
    notify "[como-votou] ETL $uf falhou" "$(printf '%s\n\n%s' "A leitura da Câmara ($uf) falhou; essa cidade segue com os dados de main." "$etl_output" | tail -c 6000)"
    git -C "$SRC" checkout -q -- "frontend/data/$lower" && git -C "$SRC" clean -fdq -- "frontend/data/$lower"
  fi
}

CITIES="$(python3 -c 'import json,sys; [print(c["uf"], c["slug"], int(bool(c.get("root")))) for c in json.load(open(sys.argv[1]))["cities"]]' "$SRC/frontend/data/cities.json")"

if [ "${SKIP_DATA:-0}" != "1" ]; then
  while read -r uf _slug _root; do
    run_etl "$uf"
  done <<< "$CITIES"
fi

key="$rev $(cd "$SRC" && "$PY" - <<'PY'
import hashlib, json, pathlib
h = hashlib.sha256()
for name in sorted(str(p) for p in pathlib.Path("frontend/data").rglob("*.generated.json")):
    data = json.loads(pathlib.Path(name).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data.pop("generated_at", None)
        for source in data.get("sources", []) if isinstance(data.get("sources"), list) else []:
            source.pop("accessed_at", None)
    h.update(name.encode())
    h.update(json.dumps(data, sort_keys=True, separators=(",", ":")).encode())
print(h.hexdigest()[:16])
PY
)"

if [ "${FORCE:-0}" != "1" ] && [ -f "$MARK" ] && [ "$(cat "$MARK")" = "$key" ]; then
  log "sem mudança ($key)"
  record "sem mudança" "$note"
  exit 0
fi

log "construindo ($key)"
(cd "$SRC/frontend" && npm ci --no-audit --no-fund --silent && ROOT="$BASE_PATH" sh scripts/build-all.sh >/dev/null)
# A cidade raiz no slug sem apagar as pastas das outras; cada uma das demais na sua pasta.
excludes=()
while read -r _uf slug isroot; do
  [ "$isroot" = 1 ] || excludes+=("--exclude=/$slug/")
done <<< "$CITIES"
mkdir -p "$DIR/site$BASE_PATH"
rsync -a --delete "${excludes[@]}" --chmod=D755,F644 "$SRC/frontend/out-all/" "$DIR/site$BASE_PATH/"
while read -r _uf slug isroot; do
  [ "$isroot" = 1 ] && continue
  mkdir -p "$DIR/site$BASE_PATH/$slug"
  rsync -a --delete --chmod=D755,F644 "$SRC/frontend/out-all/$slug/" "$DIR/site$BASE_PATH/$slug/"
done <<< "$CITIES"
echo "$key" > "$MARK"
record "publicado" "$note"
log "publicado ($key)"
