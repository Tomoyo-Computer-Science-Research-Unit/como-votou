"""São Paulo (CMSP) parsers and the SP-specific steps of the ETL, on small inline fixtures."""
from app.etl.aggregates import enrich_votacoes
from app.etl.snapshot_sp import build_votacoes, monthly_presence
from app.parsers.cmsp import (SessaoRef, fase_of, objeto_of, parse_autores, parse_membros, parse_presenca_sessao,
                              parse_session_tree, parse_votacoes_ano, parse_wp_vereadores, party_on, presence_status,
                              proposicao_of, resultado_of, veto_resultado)

VOTOS_XML = """﻿<?xml version="1.0" encoding="utf-8"?>
<CMSP>
  <Sessoes Periodo="2025" />
  <Sessao Nome="8ª Sessão Ordinária" Data="19/02/2025" />
  <Sessao Nome="9ª Sessão Ordinária" Data="20/02/2025">
    <Votacao VotacaoID="3209" TipoVotacao="Nominal" Materia="PL 177 /2025 , DO EXECUTIVO" Ementa=" Dispõe sobre a criação de órgãos" Resultado="Aprovado" Presentes="5" Sim="2" Nao="1" Abstencao="0" Branco="0" NotasRodape="Original&#09;volta em 2º&#13;&#10;">
      <Vereador Nome="ALESSANDRO GUEDES" Partido="PT" IDParlamentar="2000" Voto="Sim" />
      <Vereador Nome="AMANDA PASCHOAL" Partido="PSOL" IDParlamentar="2267" Voto="Não" />
      <Vereador Nome="ANDRÉ SANTOS" Partido="REPUBLICANOS" IDParlamentar="2150" Voto="Sim" />
    </Votacao>
    <Votacao VotacaoID="6067" TipoVotacao="Simbólica" Materia="PL 222/2013" Ementa="UBS" Resultado="Aprovado" NotasRodape="" />
  </Sessao>
</CMSP>"""

PRESENCA_XML = """﻿<?xml version="1.0" encoding="utf-8"?>
<CMSP>
  <Presencas TipoDaSessao="Ordinária" NumeroDaSessao="9" NomeDaSessao="9ª Sessão Ordinária" Data="20/02/2025" />
  <Vereador Nome="ALESSANDRO GUEDES" IDParlamentar="2000" Partido="PT" Presenca="Presente" />
  <Vereador Nome="AMANDA PASCHOAL" IDParlamentar="2267" Partido="PSOL" Presenca="Presente" />
  <Vereador Nome="ANDRÉ SANTOS" IDParlamentar="2150" Partido="REPUBLICANOS" Presenca="Presente" />
  <Vereador Nome="CELSO GIANNAZI" IDParlamentar="2185" Partido="PSOL" Presenca="Presente" />
  <Vereador Nome="CRIS MONTEIRO" IDParlamentar="2222" Partido="NOVO" Presenca="Licença&lt;sup&gt;3&lt;/sup&gt;" />
  <Vereador Nome="EDIR SALES" IDParlamentar="1000" Partido="PSD" Presenca=" " />
  <Vereador Nome="SUPLENTE" IDParlamentar="2999" Partido="PL" Presenca="*" />
</CMSP>"""


def test_session_tree_and_file_names():
    html = ('<a href="#" data_app_id="2025">x</a><a href="#" data_app_id="SESSAO 20_02_2025 9ª Sessão Ordinária">9</a>'
            '<a href="#" data_app_id="SESSAO 20_02_2025 3ª Sessão Extraordinária">3</a>')
    refs = parse_session_tree(html)
    assert [(s.data, s.tipo, s.numero) for s in refs] == [("2025-02-20", "Extraordinária", 3), ("2025-02-20", "Ordinária", 9)]
    assert refs[1].arquivo == "20_02_2025_Ordinária_9"
    assert refs[1].nome == "9ª Sessão Ordinária"


def test_presence_marks():
    assert presence_status("Presente") == "presente"
    assert presence_status("*") == "fora"
    assert presence_status("Licença<sup>4</sup>") == "licenca"
    assert presence_status(" ") == "falta"
    assert presence_status(None) == "falta"
    assert presence_status("Justificada<sup>6</sup>") == "justificada"
    s = parse_presenca_sessao(PRESENCA_XML)
    assert (s.data, s.tipo, s.numero) == ("2025-02-20", "Ordinária", 9)
    assert [r["status"] for r in s.linhas] == ["presente"] * 4 + ["licenca", "falta", "fora"]


def test_monthly_presence_contract_shape():
    rows = monthly_presence([parse_presenca_sessao(PRESENCA_XML)])
    by = {r["vereador_id"]: r for r in rows}
    assert "cmsp:2999" not in by                       # '*' = not in office: no row
    assert (by["cmsp:1000"]["faltas"], by["cmsp:1000"]["faltas_abonadas"], by["cmsp:1000"]["total_faltas"]) == (1, 0, 1)
    assert (by["cmsp:2222"]["faltas"], by["cmsp:2222"]["faltas_abonadas"], by["cmsp:2222"]["total_faltas"]) == (0, 1, 1)
    assert by["cmsp:2000"]["total_faltas"] == 0 and by["cmsp:2000"]["sessoes"] == 1
    assert {"ano", "mes", "vereador_nome", "vereador_id", "faltas", "faltas_abonadas", "total_faltas"} <= set(rows[0])


def test_votes_parse_and_absence_from_the_session_list():
    xml_votes = parse_votacoes_ano(VOTOS_XML)
    assert len(xml_votes) == 1                        # the symbolic vote is skipped
    v = xml_votes[0]
    assert (v.votacao_id, v.data, v.sessao_tipo, v.sessao_numero) == ("3209", "2025-02-20", "Ordinária", 9)
    assert [x["voto"] for x in v.votos] == ["sim", "nao", "sim"]
    sessao = parse_presenca_sessao(PRESENCA_XML)
    ref = SessaoRef("2025-02-20", 9, "Ordinária")
    ids = {"cmsp:2000", "cmsp:2267", "cmsp:2150", "cmsp:2185", "cmsp:2222", "cmsp:1000"}
    vts, stats = build_votacoes(xml_votes, [sessao], {}, ids, {ref.key: ref})
    vt = vts[0]
    assert vt["votos"] == {"cmsp:2000": "sim", "cmsp:2267": "nao", "cmsp:2150": "sim",
                           "cmsp:2185": "ausente", "cmsp:2222": "ausente", "cmsp:1000": "ausente"}
    assert "cmsp:2999" not in vt["votos"]
    assert vt["sem_voto_presentes"] == ["cmsp:2185"]     # signed in, did not vote
    assert stats["ausentes_presentes_na_sessao"] == 1 and stats["ausentes_fora_da_sessao"] == 2
    assert vt["contagem"] == {"sim": 2, "nao": 1, "abstencao": 0, "presentes_votando": 3}
    assert vt["lado_vencedor"] == "sim" and vt["resultado"] == "aprovado" and vt["objeto"] == "projeto"
    assert vt["proposicao"]["id"] == "PL-177/2025" and vt["sessao"]["fase"] == "1ª discussão"
    assert vt["fonte"].endswith("VOTACOES_20_02_2025_Ordin%C3%A1ria_9.html")
    assert stats["impresso_discrepancies"] == []
    # party on the vote wins over the roster party
    enriched = enrich_votacoes(vts, [{"id": "cmsp:2000", "partido": "PSB", "partidos_por_legislatura": {}}], [{"numero": 19, "inicio": "2025-01-01", "fim": "2028-12-31"}])
    assert enriched[0]["por_partido"]["PT"] == {"sim": 1}


def test_objeto_resultado_proposicao():
    assert objeto_of("Emenda nº 2 ao PL 416 /2025 EXECUTIVO", "") == "emenda"
    assert objeto_of("Bloco II de emendas ao PL 416 /2025", "") == "emenda"
    assert objeto_of("Cria dois blocos de emendas", "") == "requerimento"
    assert objeto_of("Adiamento de itens da pauta de vetos", "") == "requerimento"
    assert objeto_of("Rejeição aos vetos (bloco 1) ao PL 586/2023", "") == "veto"
    assert objeto_of("PL 582 /2016 , dos Vereadores NABIL BONDUKI (PT)", "SUBSTITUTIVO DA COMISSÃO\tvolta em 2º") == "substitutivo"
    assert objeto_of("PL 177 /2025 , DO EXECUTIVO", "Original\tvolta em 2º") == "projeto"
    assert objeto_of("Redação Final ao PL 447 /2021 , do EXECUTIVO", "") == "redacao_final"
    assert objeto_of("DOCREC 576-2014 TRIBUNAL DE CONTAS DO MUNICÍPIO DE...", "") == "contas"
    assert objeto_of("PL 354 /2025 , DO TRIBUNAL DE CONTAS DO MUNICIPIO", "TEXTO ORIGINAL") == "projeto"
    assert objeto_of("Votação do Parecer da Admissibilidade", "") == "parecer"
    assert objeto_of("Eleição para Corregedor da CMSP", "") == "eleicao"
    assert objeto_of("Suspensão dos trabalhos por 2 horas", "") == "requerimento"
    assert resultado_of("Reprovado") == "rejeitado" and resultado_of("Sem Quorum Suficiente") == "sem_quorum"
    assert resultado_of("Pendente de Votação") == "pendente" and resultado_of("Eleito Sargento Nantes") == "eleito"
    assert veto_resultado("Rejeição aos vetos (bloco 1)", "aprovado") == "derrubado"
    assert veto_resultado("Manutenção aos vetos (bloco 2)", "aprovado") == "mantido"
    assert proposicao_of("PLO 08/2017, da ver. EDIR SALES") == ("PLO", 8, 2017)
    assert proposicao_of("Instalação da CPI RDP 13 /2025") == ("RDP", 13, 2025)
    assert proposicao_of("Adiamento do PL 416/25") == ("PL", 416, 2025)
    assert fase_of("FASE DA DISCUSSÃO: 2ª\tORIGINAL") == "2ª discussão"
    assert fase_of("Texto Original\tVai à sanção") == "2ª discussão"


def test_ws_and_portal_parsers():
    aut = parse_autores([{"tipo": "PL", "numero": 1, "ano": 2025, "autores": [{"chave": 2205, "nome": "LUANA ALVES"}]}])
    assert aut[("PL", 1, 2025)] == [{"chave": 2205, "nome": "LUANA ALVES"}]
    fil = [{"inicio": "2016-03-01T00:00:00", "partido": {"sigla": "PSDB"}}, {"inicio": "2024-04-05T00:00:00", "partido": {"sigla": "UNIÃO"}}]
    assert party_on(fil, "2023-12-31") == "PSDB" and party_on(fil, "2024-12-31") == "UNIÃO"
    wp = parse_wp_vereadores([{"slug": "zoe-martinez", "link": "https://www.saopaulo.sp.leg.br/vereador/zoe-martinez/", "title": {"rendered": "Zoe"},
                               "meta_all": {"_cmsp_vereador_consulta_splegis_id": ["2283"], "_cmsp_vereador_name": ["Zoe Martínez"],
                                            "_cmsp_vereador_image": ["https://www.saopaulo.sp.leg.br/wp-content/uploads/2025/02/zoe_2025.jpg"]}}])
    assert wp["2283"]["nome"] == "Zoe Martínez" and wp["2283"]["foto_url"].endswith("zoe_2025.jpg")
    assert parse_membros('<a href="https://www.saopaulo.sp.leg.br/vereador/zoe-martinez/">x</a>'
                         '<a href="https://www.saopaulo.sp.leg.br/vereador/zoe-martinez/#contato">y</a>') == ["zoe-martinez"]
