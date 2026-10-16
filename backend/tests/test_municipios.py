"""Municípios do Estado do Rio: TSE (nomes, situação) e o leitor genérico do SAPL 3."""
from __future__ import annotations

from app.etl import sapl, tse_rj
from app.etl.export_static_frontend import build


def test_slugify_and_names():
    assert tse_rj.slugify("São Gonçalo") == "sao-goncalo"
    assert tse_rj.slugify("Armação dos Búzios") == "armacao-dos-buzios"
    assert tse_rj.title_name("PR JOSIAS DA CRUZ") == "PR Josias da Cruz"
    assert tse_rj.title_name("MARIA DE FÁTIMA") == "Maria de Fátima"
    assert tse_rj.situacao("ELEITO POR QP") == "eleito"
    assert tse_rj.situacao("ELEITO POR MÉDIA") == "eleito"
    assert tse_rj.situacao("SUPLENTE") == "suplente"
    assert tse_rj.situacao("#NULO") == "nao_eleito"


def _tse(pid, nome, urna, partido, sit="eleito"):
    return {"id": pid, "nome": nome, "nome_parlamentar": urna, "partido": partido,
            "partidos_por_legislatura": {"2025": partido}, "legislaturas": [], "situacao": f"{sit}_2024", "foto": None,
            "eleicoes": {"2024": {"partido": partido, "numero": "1", "votos": 100, "situacao": sit}}}


def test_match_by_name_and_party():
    tse = [_tse("tse:a", "Jose da Silva", "Zé do Posto", "PL"), _tse("tse:b", "Maria Souza", "Maria Souza", "PT"),
           _tse("tse:c", "Maria Souza", "Maria Souza", "PSD")]
    assert sapl._match(tse, "Zé do Posto", "José da Silva", None)["id"] == "tse:a"
    assert sapl._match(tse, "Maria Souza", "Maria Souza", "PSD")["id"] == "tse:c"
    assert sapl._match(tse, "Fulano", "Fulano de Tal", "PL") is None


def _raw():
    rec = lambda **k: k  # noqa: E731
    return {"base": "https://sapl.exemplo.rj.leg.br", "requests": 10, "tables": {
        "parlamentares/legislatura": {"1": rec(numero=1, data_inicio="2021-01-01", data_fim="2024-12-31"),
                                      "2": rec(numero=2, data_inicio="2025-01-01", data_fim="2028-12-31")},
        "parlamentares/parlamentar": {"10": rec(nome_completo="José da Silva", nome_parlamentar="Zé do Posto", ativo=True, email=None, fotografia=None),
                                      "11": rec(nome_completo="Ana Lima", nome_parlamentar="Ana Lima", ativo=True, email=None, fotografia=None)},
        "parlamentares/mandato": {"1": rec(parlamentar=10, legislatura=2, data_inicio_mandato=None, data_fim_mandato=None, titular=True),
                                  "2": rec(parlamentar=11, legislatura=2, data_inicio_mandato=None, data_fim_mandato=None, titular=True)},
        "parlamentares/filiacao": {"1": rec(parlamentar=10, partido=1, data="2020-01-01", data_desfiliacao=None),
                                   "2": rec(parlamentar=11, partido=2, data="2020-01-01", data_desfiliacao=None)},
        "parlamentares/partido": {"1": rec(sigla="PL"), "2": rec(sigla="PT")},
        "sessao/tiporesultadovotacao": {"1": rec(nome="Aprovado", natureza="A")},
        "materia/tipomaterialegislativa": {"1": rec(sigla="PL", descricao="Projeto de Lei"), "2": rec(sigla="IND", descricao="Indicação")},
        "base/tipoautor": {"1": rec(descricao="Parlamentar")},
        "base/autor": {"5": rec(nome="Zé do Posto", tipo=1, object_id=10)},
        "sessao/sessaoplenaria": {"100": rec(data_inicio="2025-03-04", numero=1, tipo=1, legislatura=2, __str__="1ª Sessão Ordinária")},
        "sessao/sessaoplenariapresenca": {"1": rec(sessao_plenaria=100, parlamentar=10)},
        "sessao/registrovotacao": {
            "7": rec(numero_votos_sim=1, numero_votos_nao=1, numero_abstencoes=0, tipo_resultado_votacao=1, materia=50,
                     data_hora="2025-03-04T15:00:00-03:00", __str__="Ordem: 1 - PL nº 3 de 2025 em 1ª Sessão Ordinária da 1ª Sessão Legislativa da 2ª Legislatura - Votação: Aprovado",
                     ordem=1, expediente=None),
            "8": rec(numero_votos_sim=2, numero_votos_nao=0, numero_abstencoes=0, tipo_resultado_votacao=1, materia=51,
                     data_hora="2025-03-04T15:10:00-03:00", __str__="", ordem=2, expediente=None)},
        "sessao/votoparlamentar": {"1": rec(votacao=7, parlamentar=10, voto="Sim"), "2": rec(votacao=7, parlamentar=11, voto="Não"),
                                   "3": rec(votacao=8, parlamentar=10, voto="Sim"), "4": rec(votacao=8, parlamentar=11, voto="Sim")},
        "materia/materialegislativa": {"50": rec(tipo=1, numero=3, ano=2025, ementa="Dispõe sobre praças.", data_apresentacao="2025-02-01", autores=[5]),
                                       "51": rec(tipo=2, numero=9, ano=2025, ementa="Indica poda.", data_apresentacao="2025-02-02", autores=[5])},
    }}


def test_merge_into_builds_a_snapshot_the_exporter_reads():
    snap = {"uf": "RJM", "generated_at": "2026-10-16T00:00:00+00:00",
            "legislatures": [], "vereadores": [_tse("tse:a", "Jose da Silva", "Zé do Posto", "PL")],
            "votacoes": [], "presencas": [], "proposicoes": [], "stats": {"votacoes": {}}, "sources": []}
    sapl.merge_into(snap, _raw())
    ids = {v["id"] for v in snap["vereadores"]}
    assert ids == {"tse:a", "sapl:11"}                      # Zé casou com o TSE; Ana não está na lista do TSE
    ze = next(v for v in snap["vereadores"] if v["id"] == "tse:a")
    assert ze["situacao"] == "em_exercicio" and ze["legislaturas"] == [2] and ze["partidos_por_legislatura"]["2"] == "PL"
    assert len(snap["votacoes"]) == 1                       # a indicação unânime fica de fora
    vt = snap["votacoes"][0]
    assert vt["votos"] == {"tse:a": "sim", "sapl:11": "nao"} and vt["resultado"] == "aprovado"
    assert vt["proposicao"]["id"] == "PL-3/2025" and vt["sessao"]["numero"] == "1ª Sessão Ordinária"
    assert {(p["vereador_id"], p["faltas"]) for p in snap["presencas"]} == {("tse:a", 0), ("sapl:11", 1)}
    assert sorted(p["id"] for p in snap["proposicoes"]) == ["IND-9/2025", "PL-3/2025"]
    static, per_votacao, per_vereador = build(snap)
    row = next(v for v in static["vereadores"] if v["id"] == "tse:a")
    assert row["votos"]["total"]["sim"] == 1 and row["presenca"]["por_ano"]["2025"]["faltas"] == 0
    assert per_vereador["tse:a"]["proposicoes"]
