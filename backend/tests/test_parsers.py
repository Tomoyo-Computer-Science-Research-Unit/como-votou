import json
from pathlib import Path

from app.names import norm
from app.parsers.discvot import parse_item, parse_roll_calls, parse_session_doc, parse_view_items
from app.parsers.presenca import parse_frequencia
from app.parsers.spl import parse_proposicoes
from app.parsers.vereadores import parse_vereadores_anteriores, parse_vereadores_atuais

FX = Path(__file__).parent / "fixtures"


def test_vereadores_atuais():
    vs = parse_vereadores_atuais((FX / "vereadores_atuais_3rows.html").read_text(), 11,
                                 photo_sink=lambda cvd, src: f"photos/{cvd}.jpg")
    assert [v.nome for v in vs] == ["Alana Passos", "Átila Nunes", "Carlo Caiado"]
    assert vs[0].id == "cvd:390" and vs[0].partido == "PL" and vs[0].foto == "photos/390.jpg"
    assert vs[0].email == "alana.passos@camara.rj.gov.br" and vs[0].gabinete == "Anexo - 803"


def test_vereadores_anteriores():
    vs = parse_vereadores_anteriores((FX / "anteriores_excerpt.html").read_text())
    adilson = next(v for v in vs if v.nome == "Adilson Pires")
    assert adilson.legislaturas == [3, 4, 5, 6, 7, 8] and adilson.partidos_por_legislatura["3"] == "PT"


def test_frequencia():
    p = parse_frequencia((FX / "frequencia_2026_03_excerpt.html").read_text(), 2026, 3)
    assert p.atualizado_em == "09/04/2026" and len(p.linhas) == 56
    atila = next(l for l in p.linhas if l.vereador_nome == "ÁTILA NUNES")
    assert (atila.faltas, atila.faltas_abonadas, atila.total_faltas) == (4, 4, 0)
    assert any("Rick Azevedo" in o for o in p.observacoes)


def test_spl_view():
    ps = parse_proposicoes(json.loads((FX / "scpro2124_vlei_3.json").read_text()), "vlei", "scpro2124.nsf")
    assert ps[0].id == "PL-3734/2024" and ps[0].data == "2024-12-27"
    assert ps[0].autores == ["ROSA FERNANDES"] and ps[0].autores_raw == "VEREADORA ROSA FERNANDES"
    assert ps[0].comissoes[0] == "Comissão de Justiça e Redação"
    assert "=>" not in ps[0].ementa


def test_discvot_view_items():
    items = parse_view_items(json.loads((FX / "discvot_view_expanded_8.json").read_text()))
    assert items[0].data == "2026-10-13" and items[0].num_sessao == "81ª Sessão"
    assert parse_item("Projeto De Lei 882-A/2025") == ("PL", "882-A", 2025)
    assert parse_item("Pela Ordem") is None


def test_session_doc_roll_call():
    doc = parse_session_doc((FX / "discvot_doc_pl758_2025.html").read_text())
    assert doc.data == "2026-10-13" and doc.item == "Projeto De Lei 758/2025"
    assert len(doc.votacoes) == 1
    rc = doc.votacoes[0]
    assert len(rc.sim) == 31 and rc.sim[0] == "Alana Passos" and rc.sim[-1] == "Zico"
    assert rc.nao == ["Monica Benicio", "Thais Ferreira"] and rc.abstencao == []
    assert rc.presentes_votando == 33 and rc.resultado == "aprovado"


def test_roll_call_with_abstention_and_titles():
    txt = ("(Concluída a votação nominal, constata-se que votaram SIM os Senhores Vereadores Dr. Gilberto, "
           "Vera Lins e Zico 3 (três). E que votou NÃO o Senhor Vereador Poubel 1 (um). ABSTENÇÃO a Senhora "
           "Vereadora Tainá de Paula 1 (uma). Presentes e votando 5 (cinco) senhores vereadores).\n"
           "O SR. PRESIDENTE – O Projeto está rejeitado.")
    rc = parse_roll_calls(txt)[0]
    assert rc.sim == ["Dr. Gilberto", "Vera Lins", "Zico"] and rc.nao == ["Poubel"]
    assert rc.abstencao == ["Tainá de Paula"] and rc.presentes_votando == 5 and rc.resultado == "rejeitado"


def test_norm():
    assert norm("Vereador Dr. Rogério Amorim") == norm("DR. ROGERIO AMORIM")
