# Vereadores

Câmaras Municipais do Rio de Janeiro e de São Paulo: votações nominais, presença em plenário e
proposições de cada vereador, da Tomoyo, dentro do g0v.tomoyo.systems. Um só frontend, um build
por cidade (`NEXT_PUBLIC_UF=RJ|SP`); o ETL escreve os dados de cada cidade em `frontend/data/<uf>/`.

Rio:

A Câmara não publica API nem arquivos abertos da atividade legislativa. O ETL lê as páginas do
site camara.rio e as bases Lotus Domino de aplicnt.camara.rj.gov.br: lista de vereadores,
frequência mensal, proposições do SPL e as atas de sessão, de onde as votações nominais são
extraídas por expressões regulares e conferidas contra a contagem impressa. Detalhes, contagens
reais e ressalvas em `FINDINGS.md`.

São Paulo: a Câmara publica dados abertos. O ETL lê o XML anual do painel de votações, a lista de
presença de cada sessão plenária em XML, o web service SPLegis (vereadores, filiações,
proposições e autores) e as páginas dos vereadores no portal (nome e foto). Todas as fontes trazem
o código SPLegis do vereador, e a junção é por esse código.

Sites: https://g0v.tomoyo.systems/vereadores/ (Rio) e https://g0v.tomoyo.systems/vereadores/sp/ (São Paulo).

## Layout

```text
backend/app/
  http.py                     downloads com cache, 1 req/s, checksums, cadeia TLS da Câmara do Rio
  config.py                   caminhos por UF (data/snapshot.json no Rio, data/sp/snapshot.json em SP), URLs das fontes
  parsers/vereadores.py       lista atual e legislaturas anteriores
  parsers/presenca.py         frequência mensal (POST em camara.rio)
  parsers/spl.py              visões do Sistema de Proposições Legislativas (Domino JSON)
  parsers/discvot.py          votações nominais a partir do texto das atas
  parsers/cmsp.py             São Paulo: XML de votações e de presença, árvore de sessões, SPLegis, portal
  etl/export_snapshot.py      snapshot de uma UF (--uf RJ|SP), incremental
  etl/snapshot_sp.py          o ETL de São Paulo (chamado por export_snapshot --uf SP)
  etl/export_static_frontend.py  frontend/data/<uf>: núcleo, votos por votação, votos e proposições por vereador, fotos
frontend/
  data/<uf>/static-data.generated.json         vereadores com agregados, votações com contagens, cobertura
  data/<uf>/static-votacoes/<id>.generated.json   quem votou o quê numa votação
  data/<uf>/static-vereadores/<id>.generated.json os votos e as proposições de um vereador
  data/<uf>/fotos/                               fotos (160 px)
  scripts/use-uf.sh           copia data/<uf>/ para lib/ e public/fotos/ (roda sozinho antes de build e dev)
  scripts/build-all.sh        constrói as duas cidades: out-all/ (Rio) e out-all/sp/ (São Paulo)
  lib/uf.ts                   o que muda entre as cidades: nomes, textos curtos, rótulos de tipos
  lib/method.ts               o texto da página Método de cada cidade
  app/, components/           Next.js App Router, Tailwind com tokens da tomoyo.systems
deploy/build-site.sh          roda no servidor, por cron, uma vez por dia; ETL e build das duas cidades
```

Telas: Vereadores (`/`), Votações (`/votacoes`), Presença (`/presenca`), Partidos (`/partidos`),
Método (`/metodologia`), as mesmas nas duas cidades. Teclas `1`–`5` trocam de tela, `u` troca de
cidade; setas, `v`, `e`, `r` por tela.

## Setup

```bash
cd backend && uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"
# Rio
.venv/bin/python -m app.etl.export_snapshot --all                 # ~1 h na primeira vez (1 req/s), depois incremental
.venv/bin/python -m app.etl.export_static_frontend                # frontend/data/rj
# São Paulo
.venv/bin/python -m app.etl.export_snapshot --uf SP --all         # ~20 min na primeira vez, depois ~1 min
.venv/bin/python -m app.etl.export_static_frontend --uf SP        # frontend/data/sp
cd ../frontend && npm ci && npm run dev                           # Rio; NEXT_PUBLIC_UF=SP npm run dev para São Paulo
```

Gates: `cd backend && .venv/bin/python -m pytest -q -W error`;
`cd frontend && npm run typecheck && npm run build:all && npm run test:visual` (Playwright serve as
duas cidades juntas, Rio na raiz e São Paulo em `/sp/`).

Build de produção de uma cidade só: `NEXT_PUBLIC_UF=RJ NEXT_PUBLIC_BASE_PATH=/vereadores npm run build`
ou `NEXT_PUBLIC_UF=SP NEXT_PUBLIC_BASE_PATH=/vereadores/sp npm run build` (o `prebuild` copia os
dados da cidade). As duas de uma vez, como no servidor: `ROOT=/vereadores sh scripts/build-all.sh`.

## Deploy

O site vive em `g0v.tomoyo.systems/vereadores`, no nginx estático do g0v (ver o repositório
[g0v](https://github.com/Tomoyo-Computer-Science-Research-Unit/g0v)). O cron roda
`/root/g0v/build-vereadores.sh` (cópia de `deploy/build-site.sh`, que se atualiza sozinha) todo dia:
puxa `main`, relê o que muda nas duas Câmaras, regenera os dados e, se algo mudou, constrói as duas
cidades e publica o Rio em `/root/g0v/site/vereadores/` (rsync com `--exclude=/sp/`) e São Paulo em
`/root/g0v/site/vereadores/sp/`. Se o ETL de uma cidade falha, ela segue com os dados commitados.
Falhas avisam por e-mail.
