from app.recuperacao.lexico import buscar_lexico
from tests.recuperacao.conftest import criar_documento, criar_item


def test_buscar_lexico_ranqueia_por_relevancia_e_ignora_irrelevante(db_session):
    documento = criar_documento(db_session)
    item_relevante = criar_item(
        db_session, documento, numero_item="1", item_id_canonico="lex_relevante",
        texto="aprovação aprovação aprovação do orçamento anual do centro.",
    )
    item_pouco_relevante = criar_item(
        db_session, documento, numero_item="2", item_id_canonico="lex_pouco_relevante",
        texto="aprovação do calendário letivo do próximo semestre.",
    )
    criar_item(
        db_session, documento, numero_item="3", item_id_canonico="lex_irrelevante",
        texto="relatório de manutenção predial do bloco B.",
    )

    resultados = buscar_lexico("aprovação orçamento", db_session)

    ids = [hit.item_id_canonico for hit in resultados]
    assert ids[0] == item_relevante.item_id_canonico
    assert item_pouco_relevante.item_id_canonico in ids
    assert "lex_irrelevante" not in ids
    assert resultados[0].rank == 1
    assert resultados[0].score > resultados[1].score


def test_buscar_lexico_termo_raro_pesa_mais_que_termos_comuns(db_session):
    documento = criar_documento(db_session)
    for n in range(1, 9):
        criar_item(
            db_session, documento, numero_item=f"c{n}", item_id_canonico=f"lex_comum_{n}",
            texto="decisão do setor sobre a disciplina do curso.",
        )
    criar_item(
        db_session, documento, numero_item="r", item_id_canonico="lex_codigo",
        texto="redução de vagas da disciplina COM10508 a pedido da coordenação.",
    )

    resultados = buscar_lexico("Qual foi a decisão sobre disciplina COM10508 no setor?", db_session)

    assert resultados[0].item_id_canonico == "lex_codigo"


def test_buscar_lexico_desconta_item_longo(db_session):
    documento = criar_documento(db_session)
    criar_item(
        db_session, documento, numero_item="1", item_id_canonico="lex_curto",
        texto="homologação do orçamento.",
    )
    criar_item(
        db_session, documento, numero_item="2", item_id_canonico="lex_longo",
        texto="homologação do orçamento. " + "relatório de manutenção predial do bloco B. " * 30,
    )

    resultados = buscar_lexico("homologação orçamento", db_session)

    assert [hit.item_id_canonico for hit in resultados] == ["lex_curto", "lex_longo"]


def test_buscar_lexico_empate_tem_ordem_estavel(db_session):
    documento = criar_documento(db_session)
    for sufixo in ("b", "a", "c"):
        criar_item(
            db_session, documento, numero_item=sufixo, item_id_canonico=f"lex_empate_{sufixo}",
            texto="aprovação do relatório anual.",
        )

    resultados = buscar_lexico("aprovação relatório", db_session)

    assert [hit.item_id_canonico for hit in resultados] == ["lex_empate_a", "lex_empate_b", "lex_empate_c"]


def test_buscar_lexico_so_palavras_vazias_retorna_lista_vazia(db_session):
    documento = criar_documento(db_session)
    criar_item(db_session, documento, numero_item="1", texto="aprovação do orçamento anual.")

    assert buscar_lexico("qual foi a de que", db_session) == []


def test_buscar_lexico_sem_correspondencia_retorna_lista_vazia(db_session):
    documento = criar_documento(db_session)
    criar_item(db_session, documento, numero_item="1", texto="assunto totalmente diferente.")

    resultados = buscar_lexico("termo que nao aparece em nada", db_session)

    assert resultados == []


def test_buscar_lexico_respeita_limite(db_session):
    documento = criar_documento(db_session)
    for n in range(1, 6):
        criar_item(
            db_session, documento, numero_item=str(n), item_id_canonico=f"lex_limite_{n}",
            texto="aprovação do relatório anual.",
        )

    resultados = buscar_lexico("aprovação relatório", db_session, limite=2)

    assert len(resultados) == 2


def test_buscar_lexico_pergunta_com_caracteres_especiais_nao_quebra(db_session):
    documento = criar_documento(db_session)
    criar_item(db_session, documento, numero_item="1", texto="aprovação do orçamento anual.")

    resultados = buscar_lexico("aprovação & (orçamento) | teste: 1", db_session)

    assert isinstance(resultados, list)
