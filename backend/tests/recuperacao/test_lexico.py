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
