from datetime import date

from app.grafo.construtor import construir_grafo
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta
from app.recuperacao.grafo import expandir_grafo, obter_contextos_grafo
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
        texto="PROCESSO_9001 retomada do mesmo assunto em outra sessao.",
        assunto="Reforma do laboratório de química",
    )
    construir_grafo([(documento, [item_ancora, item_relacionado])], grafo_driver)

    resultado = expandir_grafo([Hit("998001_PAUTA_1", rank=3)], grafo_driver)

    assert resultado == [Hit("998001_PAUTA_2", rank=3)]


def test_expandir_grafo_nao_reinclui_ancoras(grafo_driver):
    documento = _documento(998002)
    item_a = ItemPauta(
        item_id_canonico="998002_PAUTA_1", documento_id=998002, secao="PAUTA", numero_item="1",
        texto="1 Bolsas de iniciação científica do edital de 2025. Aprovado.", assunto="Bolsas de iniciação científica",
    )
    item_b = ItemPauta(
        item_id_canonico="998002_PAUTA_2", documento_id=998002, secao="PAUTA", numero_item="2",
        texto="2 Bolsas de iniciação científica do edital de 2025. Aprovado.", assunto="Bolsas de iniciação científica",
    )
    construir_grafo([(documento, [item_a, item_b])], grafo_driver)

    resultado = expandir_grafo([Hit("998002_PAUTA_1", rank=1), Hit("998002_PAUTA_2", rank=2)], grafo_driver)

    assert resultado == []


def test_expandir_grafo_usa_menor_rank_entre_ancoras_que_descobrem_mesmo_item(grafo_driver):
    documento = _documento(998003)
    item_a = ItemPauta(
        item_id_canonico="998003_PAUTA_1", documento_id=998003, secao="PAUTA", numero_item="1",
        texto="1 Calendário acadêmico do próximo ano letivo da graduação. Aprovado.", assunto="Calendário acadêmico do próximo ano",
    )
    item_b = ItemPauta(
        item_id_canonico="998003_PAUTA_2", documento_id=998003, secao="PAUTA", numero_item="2",
        texto="2 Calendário acadêmico do próximo ano letivo da graduação. Aprovado.", assunto="Calendário acadêmico do próximo ano",
    )
    item_c = ItemPauta(
        item_id_canonico="998003_PAUTA_3", documento_id=998003, secao="PAUTA", numero_item="3",
        texto="3 Calendário acadêmico do próximo ano letivo da graduação. Aprovado.", assunto="Calendário acadêmico do próximo ano",
    )
    construir_grafo([(documento, [item_a, item_b, item_c])], grafo_driver)

    resultado = expandir_grafo(
        [Hit("998003_PAUTA_1", rank=1), Hit("998003_PAUTA_2", rank=5)], grafo_driver
    )

    assert resultado == [Hit("998003_PAUTA_3", rank=1)]


def test_expandir_grafo_descobre_item_que_revoga_ancora(grafo_driver):
    documento = _documento(998006)
    item_antigo = ItemPauta(
        item_id_canonico="998006_PAUTA_1", documento_id=998006, secao="PAUTA", numero_item="1",
        texto="texto antigo", tipo_desfecho="Aprovado", ato_emitido="RESOLUCAO_10_2024",
    )
    item_novo = ItemPauta(
        item_id_canonico="998006_PAUTA_2", documento_id=998006, secao="PAUTA", numero_item="2",
        texto="Revoga-se a Resolução nº 10, de 1 de janeiro de 2024.", tipo_desfecho="Aprovado",
        ato_emitido="RESOLUCAO_20_2025",
    )
    construir_grafo([(documento, [item_antigo, item_novo])], grafo_driver)

    resultado = expandir_grafo([Hit("998006_PAUTA_1", rank=2)], grafo_driver)

    assert resultado == [Hit("998006_PAUTA_2", rank=2)]


def test_expandir_grafo_descobre_item_revogado_pela_ancora(grafo_driver):
    documento = _documento(998007)
    item_antigo = ItemPauta(
        item_id_canonico="998007_PAUTA_1", documento_id=998007, secao="PAUTA", numero_item="1",
        texto="texto antigo", tipo_desfecho="Aprovado", ato_emitido="RESOLUCAO_11_2024",
    )
    item_novo = ItemPauta(
        item_id_canonico="998007_PAUTA_2", documento_id=998007, secao="PAUTA", numero_item="2",
        texto="Revoga-se a Resolução nº 11, de 1 de janeiro de 2024.", tipo_desfecho="Aprovado",
        ato_emitido="RESOLUCAO_21_2025",
    )
    construir_grafo([(documento, [item_antigo, item_novo])], grafo_driver)

    resultado = expandir_grafo([Hit("998007_PAUTA_2", rank=4)], grafo_driver)

    assert resultado == [Hit("998007_PAUTA_1", rank=4)]


def test_expandir_grafo_sem_ancoras_retorna_vazio(grafo_driver):
    assert expandir_grafo([], grafo_driver) == []


def test_obter_contextos_grafo_traz_departamento_sem_mencao_textual_no_item(grafo_driver):
    # valida a pendencia registrada: o item nunca menciona "DCC" no texto, so
    # a Ata (via PERTENCE_A) sabe o departamento.
    documento = _documento(998004, departamento="DCC")
    item = ItemPauta(
        item_id_canonico="998004_PAUTA_1", documento_id=998004, secao="PAUTA", numero_item="1",
        texto="aprovacao de um pedido qualquer sem mencionar o departamento de origem.",
    )
    construir_grafo([(documento, [item])], grafo_driver)

    contextos = obter_contextos_grafo(["998004_PAUTA_1"], grafo_driver)

    assert contextos["998004_PAUTA_1"]["departamento"] == "DCC"
    assert contextos["998004_PAUTA_1"]["centro"] == "CT"


def test_obter_contextos_grafo_traz_deliberacao_e_relacionadas(grafo_driver):
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

    contextos = obter_contextos_grafo(["998005_PAUTA_2"], grafo_driver)
    contexto = contextos["998005_PAUTA_2"]

    assert contexto["tipo_desfecho"] == "Aprovado"
    assert contexto["resultado_votacao"] == "unanimidade"
    assert contexto["ato_emitido"] == "RESOLUCAO_20_2025"
    assert contexto["encaminhamento"] == "publicar no boletim"
    assert contexto["deliberacoes_relacionadas"] == [
        {"tipo_relacao": "revoga", "item_id_canonico": "998005_PAUTA_1", "ato_emitido": "RESOLUCAO_10_2024"}
    ]


def test_obter_contextos_grafo_traz_deliberacao_revogada_pela_ancora(grafo_driver):
    documento = _documento(998008)
    item_antigo = ItemPauta(
        item_id_canonico="998008_PAUTA_1", documento_id=998008, secao="PAUTA", numero_item="1",
        texto="texto antigo", tipo_desfecho="Aprovado", ato_emitido="RESOLUCAO_12_2024",
    )
    item_novo = ItemPauta(
        item_id_canonico="998008_PAUTA_2", documento_id=998008, secao="PAUTA", numero_item="2",
        texto="Revoga-se a Resolução nº 12, de 1 de janeiro de 2024.", tipo_desfecho="Aprovado",
        ato_emitido="RESOLUCAO_22_2025",
    )
    construir_grafo([(documento, [item_antigo, item_novo])], grafo_driver)

    contextos = obter_contextos_grafo(["998008_PAUTA_1"], grafo_driver)

    assert contextos["998008_PAUTA_1"]["deliberacoes_relacionadas"] == [
        {"tipo_relacao": "revogado_por", "item_id_canonico": "998008_PAUTA_2", "ato_emitido": "RESOLUCAO_22_2025"}
    ]


def test_obter_contextos_grafo_item_inexistente_retorna_campos_none(grafo_driver):
    contextos = obter_contextos_grafo(["nao_existe_no_grafo"], grafo_driver)

    assert contextos["nao_existe_no_grafo"]["departamento"] is None
    assert contextos["nao_existe_no_grafo"]["deliberacoes_relacionadas"] == []


def test_obter_contextos_grafo_isola_contexto_por_item_numa_unica_chamada(grafo_driver):
    documento = _documento(998009, departamento="DCC")
    item_a = ItemPauta(
        item_id_canonico="998009_PAUTA_1", documento_id=998009, secao="PAUTA", numero_item="1",
        texto="texto a", tipo_desfecho="Aprovado", ato_emitido="RESOLUCAO_30_2025",
    )
    item_b = ItemPauta(
        item_id_canonico="998009_PAUTA_2", documento_id=998009, secao="PAUTA", numero_item="2",
        texto="texto b", tipo_desfecho="Rejeitado",
    )
    construir_grafo([(documento, [item_a, item_b])], grafo_driver)

    contextos = obter_contextos_grafo(
        ["998009_PAUTA_1", "998009_PAUTA_2", "nao_existe_no_grafo"], grafo_driver
    )

    assert contextos["998009_PAUTA_1"]["tipo_desfecho"] == "Aprovado"
    assert contextos["998009_PAUTA_1"]["ato_emitido"] == "RESOLUCAO_30_2025"
    assert contextos["998009_PAUTA_2"]["tipo_desfecho"] == "Rejeitado"
    assert contextos["998009_PAUTA_2"]["ato_emitido"] is None
    assert contextos["998009_PAUTA_1"]["departamento"] == "DCC"
    assert contextos["998009_PAUTA_2"]["departamento"] == "DCC"
    assert contextos["nao_existe_no_grafo"]["departamento"] is None


def test_rastrear_expansao_mostra_cada_ancora_que_chega_ao_item(grafo_driver):
    from app.recuperacao.grafo import rastrear_expansao

    documento = _documento(998101)
    itens = [
        ItemPauta(
            item_id_canonico=f"998101_PAUTA_{n}", documento_id=998101, secao="PAUTA", numero_item=str(n),
            texto=f"{n} Calendário de provas do semestre letivo de 2025. Aprovado.", assunto="Calendário de provas do semestre",
        )
        for n in (1, 2, 3)
    ]
    construir_grafo([(documento, itens)], grafo_driver)
    ancoras = [Hit("998101_PAUTA_1", rank=1), Hit("998101_PAUTA_2", rank=4)]

    caminhos = rastrear_expansao(ancoras, grafo_driver)
    expandidos = expandir_grafo(ancoras, grafo_driver)

    ate_o_terceiro = [c for c in caminhos if c["item_id_canonico"] == "998101_PAUTA_3"]
    assert [(c["ancora"], c["rank_ancora"], c["relacao"]) for c in ate_o_terceiro] == [
        ("998101_PAUTA_1", 1, "TRATA_DE"), ("998101_PAUTA_2", 4, "TRATA_DE"),
    ]
    assert all(c["via"] for c in ate_o_terceiro)
    assert expandidos == [Hit("998101_PAUTA_3", rank=1)]


def test_expandir_grafo_nao_devolve_fragmento_do_proprio_item_ancora(grafo_driver):
    documento = _documento(998201)
    fragmento0 = ItemPauta(
        item_id_canonico="998201_PAUTA_1", documento_id=998201, secao="PAUTA", numero_item="1",
        texto="1 PROCESSO_9101 relatório longo, primeira parte.", assunto="Relatório", fragmento_indice=0,
    )
    fragmento1 = ItemPauta(
        item_id_canonico="998201_PAUTA_1_F1", documento_id=998201, secao="PAUTA", numero_item="1",
        texto="segunda parte do relatório.", assunto="Relatório", fragmento_indice=1,
    )
    outro = ItemPauta(
        item_id_canonico="998201_PAUTA_2", documento_id=998201, secao="PAUTA", numero_item="2",
        texto="2 PROCESSO_9101 homologação do relatório.", assunto="Relatório",
    )
    construir_grafo([(documento, [fragmento0, fragmento1, outro])], grafo_driver)

    resultado = expandir_grafo([Hit("998201_PAUTA_1", rank=2)], grafo_driver)

    assert resultado == [Hit("998201_PAUTA_2", rank=2)]
