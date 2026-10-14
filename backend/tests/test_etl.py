"""Outcome/presiding-officer detection, party majority and the static export shape (small fixtures)."""
import json

import pytest

from app.etl import export_static_frontend as esf
from app.etl.aggregates import enrich_votacoes, lado_vencedor, party_breakdown, party_majority, vereador_aggregates
from app.etl.export_snapshot import roster_for_date
from app.names import NameResolver, split_authors
from app.parsers.discvot import detect_resultado, number_words, parse_roll_calls

RC = ("(Concluída a votação nominal, constata-se que votaram SIM os Senhores Vereadores Alana Passos, Carlo Caiado "
      "e Zico 3 (três). E que votou NÃO o Senhor Vereador Poubel 1 (um). Presentes e votando 4 (quatro) senhores vereadores).\n")


@pytest.mark.parametrize("after, expected", [
    ("O SR. PRESIDENTE (CARLO CAIADO) – O Projeto de Lei nº 1/2025 está aprovado.", "aprovado"),
    ("O Projeto de Lei Complementar nº 49/2025 foi aprovado e voltará em 2ª discussão.", "aprovado"),
    ("A Emenda nº 17 está rejeitada e segue ao arquivo.", "rejeitado"),
    ("Presentes e votando NÃO 26 (vinte e seis) vereadores. O veto foi rejeitado e o Projeto segue à promulgação.", "derrubado"),
    ("Os vetos parciais ao Projeto de Lei nº 2113-A/2023 estão mantidos e os dispositivos vetados seguem ao arquivo.", "mantido"),
    ("Os vetos parciais estão rejeitados e os dispositivos vetados seguem à promulgação.", "derrubado"),
    ("O Projeto de Lei Complementar nº 16/2025, assim emendado, está prejudicado e segue ao arquivo.", "prejudicado"),
    ("Presentes 8 (oito) senhores vereadores.\nNão há quórum para deliberar sobre a matéria, que voltará em votação.", "sem_quorum"),
    ("Presentes e votando SIM 32 (trinta e dois) senhores vereadores.\nAprovado.\nEm votação o projeto assim emendado.", "aprovado"),
    ("Votaram SIM 33 senhores vereadores.\nAprovado o bloco de Emendas 2, 3 e 4 ao Projeto de Lei nº 2906-A/2024.", "aprovado"),
    ("A Emenda nº 1 está provada.", "aprovado"),
    ("não tendo sofrido emenda de redação, fica considerada aprovada a redação final do Projeto de Lei nº 363-A/2025", "aprovado"),
    ("Para declaração de voto, o nobre Vereador X, que dispõe de três minutos.", None),
])
def test_detect_resultado(after, expected):
    assert detect_resultado(after)[0] == expected


def test_resultado_window_stops_at_next_roll_call():
    txt = RC + "Presentes 4 (quatro). Não há quórum para deliberar sobre a matéria.\nEm votação a Emenda nº 2.\n" + RC + \
          "A Emenda nº 2 está aprovada.\n"
    rcs = parse_roll_calls(txt)
    assert [r.resultado for r in rcs] == ["sem_quorum", "aprovado"]
    assert rcs[1].objeto == "emenda"


def test_veto_objeto_and_derrubado():
    txt = "REJEIÇÃO AO VETO, Relator VEREADOR X.\nEm votação.\n" + RC.replace("SIM", "NÃO", 1) + \
          "O SR. PRESIDENTE (CARLO CAIADO) – Presentes e votando NÃO 4. Está rejeitado e o Projeto segue à promulgação.\n"
    rc = parse_roll_calls(txt)[0]
    assert rc.objeto == "veto" and rc.resultado == "derrubado"


def test_presiding_officer_detection():
    txt = "O SR. PRESIDENTE (CARLO CAIADO) – Em votação.\n" + RC + "A SRA. PRESIDENTE (TÂNIA BASTOS) – Está aprovado.\n"
    rc = parse_roll_calls(txt)[0]
    assert rc.presidente == "TÂNIA BASTOS"          # the officer who announces the result
    txt2 = "Presidência do Vereador Willian Coelho\n" + RC + "Está aprovado.\n"
    assert parse_roll_calls(txt2)[0].presidente == "Willian Coelho"


def test_printed_count_prefers_words():
    txt = RC.replace("e Zico 3 (três)", "e Zico 2a3 (três)")
    rc = parse_roll_calls(txt)[0]
    assert rc.impresso == {"sim": 3, "nao": 1} and len(rc.sim) == 3
    assert number_words("trinta e um") == 31 and number_words("quarenta") == 40 and number_words("foo") is None


VEREADORES = [
    {"id": "cvd:1", "nome": "Alana Passos", "nome_parlamentar": "Alana Passos", "partido": "PL", "partidos_por_legislatura": {"12": "PL"}},
    {"id": "cvd:2", "nome": "Carlo Caiado", "nome_parlamentar": "Carlo Caiado", "partido": "PSD", "partidos_por_legislatura": {"12": "PSD"}},
    {"id": "cvd:3", "nome": "Zico", "nome_parlamentar": "Zico", "partido": "PL", "partidos_por_legislatura": {"12": "PL"}},
    {"id": "cvd:4", "nome": "Poubel", "nome_parlamentar": "Poubel", "partido": "PL", "partidos_por_legislatura": {"12": "PL"}},
    {"id": "cvd:5", "nome": "Dr. Gilberto", "nome_parlamentar": "Dr. Gilberto", "partido": "PSD", "partidos_por_legislatura": {"12": "PSD"}},
]
LEGS = [{"numero": 12, "inicio": "2025-01-01", "fim": "2028-12-31"}]
PARTY = {"cvd:1": "PL", "cvd:2": "PSD", "cvd:3": "PL", "cvd:4": "PL", "cvd:5": "PSD"}


def test_party_majority_and_breakdown():
    votos = {"cvd:1": "sim", "cvd:3": "sim", "cvd:4": "nao", "cvd:2": "sim", "cvd:5": "presidindo"}
    assert party_majority(votos, PARTY, "PL") == "sim"
    assert party_majority(votos, PARTY, "PSD") is None          # only one PSD member voted
    assert party_majority({"cvd:1": "sim", "cvd:3": "nao"}, PARTY, "PL") is None   # tie
    assert party_breakdown(votos, PARTY) == {"PL": {"sim": 2, "nao": 1}, "PSD": {"sim": 1}}
    assert lado_vencedor({"sim": 3, "nao": 1}) == "sim" and lado_vencedor({"sim": 1, "nao": 1}) is None
    assert lado_vencedor({"sim": 0, "nao": 0}) is None


def _snapshot():
    votacoes = [
        {"id": "u1:0", "data": "2025-03-04", "hora": None, "sessao": {"tipo": "Sessão Ordinária", "numero": "1ª Sessão", "fase": "Ordem do Dia"},
         "proposicao": {"id": "PL-1/2025", "tipo": "PL", "numero": "1", "ano": 2025, "ementa": "E" * 300, "autores": ["ZICO"], "autores_ids": ["cvd:3"]},
         "objeto": "projeto", "resultado": "aprovado", "resultado_frase": "x", "contagem": {"sim": 3, "nao": 1, "abstencao": 0, "presentes_votando": 4},
         "presidente": "cvd:5", "roster_mes": "2025-03",
         "votos": {"cvd:1": "sim", "cvd:3": "sim", "cvd:4": "nao", "cvd:2": "sim", "cvd:5": "presidindo"}, "fonte": "https://x/u1?OpenDocument"},
        {"id": "u2:0", "data": "2025-03-05", "hora": None, "sessao": {"tipo": "Sessão Ordinária", "numero": "2ª Sessão", "fase": "Ordem do Dia"},
         "proposicao": {"id": "PL-2/2025", "tipo": "PL", "numero": "2", "ano": 2025, "ementa": "b", "autores": [], "autores_ids": []},
         "objeto": "veto", "resultado": "derrubado", "resultado_frase": "x", "contagem": {"sim": 0, "nao": 3, "abstencao": 1, "presentes_votando": 4},
         "presidente": "cvd:2", "roster_mes": "2025-03",
         "votos": {"cvd:1": "nao", "cvd:3": "nao", "cvd:4": "abstencao", "cvd:2": "nao", "cvd:5": "ausente"}, "fonte": "https://x/u2?OpenDocument"},
    ]
    presencas = [{"ano": 2025, "mes": 3, "vereador_nome": "ALANA PASSOS", "faltas": 2, "faltas_abonadas": 1, "total_faltas": 1, "vereador_id": "cvd:1"},
                 {"ano": 2025, "mes": 4, "vereador_nome": "ALANA PASSOS", "faltas": 0, "faltas_abonadas": 0, "total_faltas": 0, "vereador_id": "cvd:1"}]
    proposicoes = [{"id": "PL-1/2025", "tipo": "PL", "numero": "1", "ano": 2025, "ementa": "E", "data": "2025-02-01", "autores": ["ZICO", "POUBEL"],
                    "autores_raw": "VEREADOR ZICO E VEREADOR POUBEL", "autores_ids": ["cvd:3", "cvd:4"], "autores_outros": False, "comissoes": [], "unid": "x", "legislatura_db": "scpro.nsf"},
                   {"id": "REQINF-9/2026", "tipo": "REQINF", "numero": "9", "ano": 2026, "ementa": "R", "data": "2026-01-10", "autores": ["ZICO"],
                    "autores_raw": "VEREADOR ZICO", "autores_ids": ["cvd:3"], "autores_outros": False, "comissoes": [], "unid": "y", "legislatura_db": "scpro.nsf"}]
    vs = [dict(v, legislaturas=[12], situacao="em_exercicio", foto="photos/1.jpg" if v["id"] == "cvd:1" else None,
               gabinete=None, telefone=None, email=None, perfil_url=None) for v in VEREADORES]
    return {"generated_at": "2026-10-14T00:00:00+00:00", "legislatures": LEGS, "vereadores": vs, "votacoes": votacoes,
            "presencas": presencas, "proposicoes": proposicoes,
            "stats": {"votacoes": {"candidates_in_range": 2, "docs_fetched": 2, "docs_with_roll_call": 2, "por_ano": {"2025": {"candidatos": 2, "lidos": 2}},
                                   "unmatched_names": {}, "contagem_mismatches": 0, "impresso_discrepancies": [], "docs_failed": []},
                      "proposicoes": {"unmatched_authors": {}}, "presenca_unmatched": []},
            "sources": [{"name": "GET https://x", "url": "https://x/discvot.nsf/" + "a" * 32 + "/" + "b" * 32 + "?OpenDocument", "accessed_at": "2026-10-14T00:00:00+00:00"}]}


def test_vereador_aggregates():
    snap = _snapshot()
    vts = enrich_votacoes(snap["votacoes"], snap["vereadores"], LEGS)
    assert vts[0]["lado_vencedor"] == "sim" and vts[0]["por_partido"]["PL"] == {"sim": 2, "nao": 1}
    agg = vereador_aggregates(snap["vereadores"], vts, snap["presencas"], snap["proposicoes"], LEGS)
    zico = agg["cvd:3"]
    assert zico["votos"]["por_ano"]["2025"] == {"sim": 1, "nao": 1, "abstencao": 0, "ausente": 0, "presidindo": 0}
    assert zico["participacao"] == 1.0 and zico["com_maioria"] == 1.0 and zico["contra_partido"] == 0 and zico["contra_partido_taxa"] == 0.0
    assert zico["proposicoes_por_tipo"] == {"PL": {"2025": 1}, "REQINF": {"2026": 1}} and zico["proposicoes_total"] == 2
    poubel = agg["cvd:4"]
    assert poubel["com_maioria"] == 0.0 and poubel["contra_partido"] == 1 and poubel["contra_partido_taxa"] == 1.0
    gil = agg["cvd:5"]
    assert gil["votos"]["total"]["presidindo"] == 1 and gil["votos"]["total"]["ausente"] == 1 and gil["participacao"] == 0.0
    alana = agg["cvd:1"]
    assert alana["presenca"]["por_ano"]["2025"] == {"faltas": 2, "abonadas": 1, "total": 1, "meses": 2}
    assert alana["presenca"]["por_mes"]["2025-03"] == {"faltas": 2, "abonadas": 1, "total": 1}


def test_export_shape(tmp_path):
    snap = _snapshot()
    static, per_vot, per_ver = esf.build(snap)
    assert {"generated_at", "legislaturas", "vereadores", "votacoes", "presenca_meses", "stats", "sources"} <= set(static)
    row = static["votacoes"][0]
    assert row["id"] == "u2:0" and row["data"] == "2025-03-05"           # newest first
    assert "votos" not in row and row["por_partido"] == {"PL": {"nao": 2, "abstencao": 1}, "PSD": {"nao": 1}}
    assert row["sessao"]["numero"] == "2ª Sessão" and row["fonte"].endswith("?OpenDocument") and row["proposicao"]["autores"] == []
    assert static["votacoes"][1]["proposicao"]["ementa"].endswith("…") and len(static["votacoes"][1]["proposicao"]["ementa"]) <= esf.EMENTA_MAX
    v1 = next(v for v in static["vereadores"] if v["id"] == "cvd:1")
    assert v1["foto"] == "fotos/1.jpg" and v1["presenca"]["por_mes"]["2025-04"] == {"faltas": 0, "abonadas": 0, "total": 0}
    assert v1["presenca"]["por_ano"]["2025"]["meses"] == 2 and v1["totais"]["votacoes_registradas"] == 2
    assert static["stats"]["votacoes"]["total"] == 2 and static["stats"]["presenca"]["ultimo_mes"] == "2025-04"
    assert per_vot["u1:0"]["votos"]["cvd:5"] == "presidindo" and per_vot["u1:0"]["por_partido"]["PSD"]["sim"] == 1
    zico = per_ver["cvd:3"]
    assert [v["votacao_id"] for v in zico["votos"]] == ["u2:0", "u1:0"]
    assert zico["proposicoes"][0]["id"] == "REQINF-9/2026" and zico["proposicoes"][1]["coautores"] == ["cvd:4"]
    assert esf.fs_id("cvd:390") == "cvd-390" and esf.fs_id("u1:0") == "u1-0"
    # files on disk
    (tmp_path / "snap.json").write_text(json.dumps(snap))
    esf.main(["--snapshot", str(tmp_path / "snap.json"), "--out", str(tmp_path / "lib"), "--no-fotos"])
    assert (tmp_path / "lib" / "static-data.generated.json").exists()
    assert (tmp_path / "lib" / "static-votacoes" / "u1-0.generated.json").exists()
    assert json.loads((tmp_path / "lib" / "static-vereadores" / "cvd-3.generated.json").read_text())["id"] == "cvd:3"


def test_roster_for_date_falls_back_to_latest_month():
    ex = {(2026, 8): {"a", "b"}, (2026, 9): {"a", "c"}}
    assert roster_for_date("2026-09-15", ex) == ({"a", "c"}, "2026-09")
    assert roster_for_date("2026-10-13", ex) == ({"a", "c"}, "2026-09")
    assert roster_for_date("2026-07-01", ex) == (set(), None)


def test_name_resolver_and_authors():
    r = NameResolver(VEREADORES)
    assert r.resolve("Vereadora ALANA PASSOS") == ["cvd:1"] and r.resolve("Gilberto") == ["cvd:5"]
    assert r.resolve("Zico Poubel") == ["cvd:3", "cvd:4"]           # missing comma between two names
    assert r.resolve("Fulano de Tal") == [] and r.unmatched == {"Fulano de Tal": 1}
    assert split_authors("VEREADOR ZICO, VEREADORA ALANA PASSOS E VEREADOR POUBEL E OUTROS") == ["ZICO", "ALANA PASSOS", "POUBEL"]
    assert split_authors("COMISSÃO DE TRABALHO, EMPREGO E RENDA") == ["COMISSÃO DE TRABALHO, EMPREGO E RENDA"]
    assert split_authors("VEREADORES ZICO E POUBEL E DAS COMISSÕES DE JUSTIÇA E REDAÇÃO, DE EDUCAÇÃO E DO VEREADOR DR. GILBERTO") == \
        ["ZICO", "POUBEL", "COMISSÕES DE JUSTIÇA E REDAÇÃO, DE EDUCAÇÃO", "DR. GILBERTO"]
