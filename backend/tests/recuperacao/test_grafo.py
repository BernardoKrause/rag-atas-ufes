from datetime import date

from app.grafo.construtor import construir_grafo
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta
from app.recuperacao.grafo import expandir_grafo, obter_contexto_grafo
from app.recuperacao.tipos import Hit


def _documento(id_documento, **overrides):
    base = dict(
        id_documento=id_documento, nome_arquivo=f"{id_documento}.pdf", url_origem="x.pdf", centro="CT",
        campus="Goiabeiras", tipo_orgao="B", orgao="CT", texto_limpo="texto", data_reuniao=date(2025, 1, 1),
    )
    base.update(overrides)
    return Documento(**base)


def test_expandir_grafo_descobre_item_relacionado_por_assunto(grafo_driver):
    documento = _documento(998001)
    item_ancora = ItemPauta(
        item_id_canonico="998001_PAUTA_1", documento_id=998001, secao="PAUTA", numero_item="1",
        texto="PROCESSO_9001 discussao do assunto.", assunto="Reforma do laboratório de química",
    )
    item_relacionado = ItemPauta(
        item_id_canonico="998001_PAUTA_2", documento_id=998001, secao="PAUTA", numero_item="2",
        texto="PROCESSO_9002 retomada do mesmo assunto em outra sessao.",
        assunto="Reforma do laboratório de química",
    )
    construir_grafo([(documento, [item_ancora, item_relacionado])], grafo_driver)

    resultado = expandir_grafo([Hit("998001_PAUTA_1", rank=3)], grafo_driver)

    assert resultado == [Hit("998001_PAUTA_2", rank=3)]


def test_expandir_grafo_nao_reinclui_ancoras(grafo_driver):
    documento = _documento(998002)
    item_a = ItemPauta(
        item_id_canonico="998002_PAUTA_1", documento_id=998002, secao="PAUTA", numero_item="1",
        texto="texto a.", assunto="Bolsas de iniciação científica",
    )
    item_b = ItemPauta(
        item_id_canonico="998002_PAUTA_2", documento_id=998002, secao="PAUTA", numero_item="2",
        texto="texto b.", assunto="Bolsas de iniciação científica",
    )
    construir_grafo([(documento, [item_a, item_b])], grafo_driver)

    resultado = expandir_grafo([Hit("998002_PAUTA_1", rank=1), Hit("998002_PAUTA_2", rank=2)], grafo_driver)

    assert resultado == []


def test_expandir_grafo_usa_menor_rank_entre_ancoras_que_descobrem_mesmo_item(grafo_driver):
    documento = _documento(998003)
    item_a = ItemPauta(
        item_id_canonico="998003_PAUTA_1", documento_id=998003, secao="PAUTA", numero_item="1",
        texto="texto a.", assunto="Calendário acadêmico do próximo ano",
    )
    item_b = ItemPauta(
        item_id_canonico="998003_PAUTA_2", documento_id=998003, secao="PAUTA", numero_item="2",
        texto="texto b.", assunto="Calendário acadêmico do próximo ano",
    )
    item_c = ItemPauta(
        item_id_canonico="998003_PAUTA_3", documento_id=998003, secao="PAUTA", numero_item="3",
        texto="texto c.", assunto="Calendário acadêmico do próximo ano",
    )
    construir_grafo([(documento, [item_a, item_b, item_c])], grafo_driver)

    resultado = expandir_grafo(
        [Hit("998003_PAUTA_1", rank=1), Hit("998003_PAUTA_2", rank=5)], grafo_driver
    )

    assert resultado == [Hit("998003_PAUTA_3", rank=1)]


def test_expandir_grafo_sem_ancoras_retorna_vazio(grafo_driver):
    assert expandir_grafo([], grafo_driver) == []


def test_obter_contexto_grafo_traz_departamento_sem_mencao_textual_no_item(grafo_driver):
    # valida a pendencia registrada: o item nunca menciona "DCC" no texto, so
    # a Ata (via PERTENCE_A) sabe o departamento.
    documento = _documento(998004, departamento="DCC")
    item = ItemPauta(
        item_id_canonico="998004_PAUTA_1", documento_id=998004, secao="PAUTA", numero_item="1",
        texto="aprovacao de um pedido qualquer sem mencionar o departamento de origem.",
    )
    construir_grafo([(documento, [item])], grafo_driver)

    contexto = obter_contexto_grafo("998004_PAUTA_1", grafo_driver)

    assert contexto["departamento"] == "DCC"
    assert contexto["centro"] == "CT"


def test_obter_contexto_grafo_traz_deliberacao_e_relacionadas(grafo_driver):
    documento = _documento(998005)
    item_antigo = ItemPauta(
        item_id_canonico="998005_PAUTA_1", documento_id=998005, secao="PAUTA", numero_item="1",
        texto="texto antigo", tipo_desfecho="Aprovado", ato_emitido="RESOLUCAO_10_2024",
    )
    item_novo = ItemPauta(
        item_id_canonico="998005_PAUTA_2", documento_id=998005, secao="PAUTA", numero_item="2",
        texto="Revoga-se a Resolução nº 10, de 1 de janeiro de 2024.",
        tipo_desfecho="Aprovado", resultado_votacao="unanimidade", ato_emitido="RESOLUCAO_20_2025",
        encaminhamento="publicar no boletim",
    )
    construir_grafo([(documento, [item_antigo, item_novo])], grafo_driver)

    contexto = obter_contexto_grafo("998005_PAUTA_2", grafo_driver)

    assert contexto["tipo_desfecho"] == "Aprovado"
    assert contexto["resultado_votacao"] == "unanimidade"
    assert contexto["ato_emitido"] == "RESOLUCAO_20_2025"
    assert contexto["encaminhamento"] == "publicar no boletim"
    assert contexto["deliberacoes_relacionadas"] == [
        {"tipo_relacao": "revoga", "item_id_canonico": "998005_PAUTA_1", "ato_emitido": "RESOLUCAO_10_2024"}
    ]


def test_obter_contexto_grafo_item_inexistente_retorna_campos_none(grafo_driver):
    contexto = obter_contexto_grafo("nao_existe_no_grafo", grafo_driver)

    assert contexto["departamento"] is None
    assert contexto["deliberacoes_relacionadas"] == []
