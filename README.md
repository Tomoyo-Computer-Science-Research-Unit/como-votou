# Como votou seu vereador

Câmara Municipal do Rio de Janeiro: votações nominais, presença em plenário e proposições de cada
vereador, da Tomoyo, dentro do g0v.tomoyo.systems.

A Câmara não publica API nem arquivos abertos da atividade legislativa. O ETL lê as páginas do
site camara.rio e as bases Lotus Domino de aplicnt.camara.rj.gov.br: lista de vereadores,
frequência mensal, proposições do SPL e as atas de sessão, de onde as votações nominais são
extraídas por expressões regulares e conferidas contra a contagem impressa. Detalhes, contagens
reais e ressalvas em `FINDINGS.md`.

Site: https://g0v.tomoyo.systems/vereadores/

## Layout

```text
backend/app/
  http.py                     downloads com cache, 1 req/s, checksums, cadeia TLS da Câmara
  parsers/vereadores.py       lista atual e legislaturas anteriores
  parsers/presenca.py         frequência mensal (POST em camara.rio)
  parsers/spl.py              visões do Sistema de Proposições Legislativas (Domino JSON)
  parsers/discvot.py          votações nominais a partir do texto das atas
  etl/export_snapshot.py      data/snapshot.json, incremental
  etl/export_static_frontend.py  frontend/lib: núcleo, votos por votação, votos e proposições por vereador
frontend/
  lib/static-data.generated.json         vereadores com agregados, votações com contagens, cobertura
  lib/static-votacoes/<id>.generated.json   quem votou o quê numa votação
  lib/static-vereadores/<id>.generated.json os votos e as proposições de um vereador
  app/, components/           Next.js App Router, Tailwind com tokens da tomoyo.systems
deploy/build-site.sh          roda no servidor, por cron, uma vez por dia
```

Telas: Vereadores (`/`), Votações (`/votacoes`), Presença (`/presenca`), Partidos (`/partidos`),
Método (`/metodologia`). Teclas `1`–`5` trocam de tela; setas, `v`, `e`, `r` por tela.

## Setup

```bash
cd backend && uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m app.etl.export_snapshot          # ~25 min na primeira vez (1 req/s), depois incremental
.venv/bin/python -m app.etl.export_static_frontend
cd ../frontend && npm ci && npm run dev
```

Gates: `cd backend && .venv/bin/python -m pytest -q -W error`; `cd frontend && npx tsc --noEmit && npm run build && npm run test:visual`.

## Deploy

O site vive em `g0v.tomoyo.systems/vereadores`, no nginx estático do g0v (ver o repositório
[g0v](https://github.com/Tomoyo-Computer-Science-Research-Unit/g0v)). O cron roda
`/root/g0v/build-vereadores.sh` (cópia de `deploy/build-site.sh`, que se atualiza sozinha) todo dia:
puxa `main`, relê o que muda na Câmara, regenera os dados e, se algo mudou, constrói e publica.
Falhas avisam por e-mail.
