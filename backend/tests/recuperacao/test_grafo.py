from datetime import date

from app.grafo.construtor import construir_grafo
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta
from app.recuperacao.grafo import expandir_grafo
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
        texto="texto a.", assunto="Bolsas de pesquisa",
    )
    item_b = ItemPauta(
        item_id_canonico="998002_PAUTA_2", documento_id=998002, secao="PAUTA", numero_item="2",
        texto="texto b.", assunto="Bolsas de pesquisa",
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
