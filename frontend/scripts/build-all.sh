#!/usr/bin/env sh
# Constrói todas as cidades de data/cities.json e junta num só diretório servível, como no servidor:
#   out-all/          a cidade raiz (root=true), base "$ROOT"
#   out-all/<slug>/   cada uma das demais, base "$ROOT/<slug>"
# ROOT vazio serve na raiz (testes); em produção o deploy usa ROOT=/vereadores e publica cada pasta.
set -eu
cd "$(dirname "$0")/.."
ROOT="${ROOT:-}"
rm -rf out out-all out-cities .next
mkdir -p out-cities
node -e 'for (const c of require("./data/cities.json").cities) console.log(c.uf, c.slug, c.root ? 1 : 0)' > out-cities/list
while read -r uf slug isroot; do
  if [ "$isroot" = 1 ]; then base="$ROOT"; else base="$ROOT/$slug"; fi
  rm -rf .next
  NEXT_PUBLIC_UF="$uf" NEXT_PUBLIC_BASE_PATH="$base" npm run build --silent >/dev/null
  mv out "out-cities/$slug"
  echo "build-all: $uf em ${base:-/}"
done < out-cities/list
rootslug="$(awk '$3 == 1 { print $2; exit }' out-cities/list)"
mv "out-cities/$rootslug" out-all
while read -r uf slug isroot; do
  [ "$isroot" = 1 ] || mv "out-cities/$slug" "out-all/$slug"
done < out-cities/list
rm -rf out-cities
