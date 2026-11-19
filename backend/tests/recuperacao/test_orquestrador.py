from sqlalchemy import text

from app.grafo.construtor import construir_grafo
from app.ingestion.indexador import indexar_e_persistir
from app.recuperacao.orquestrador import recuperar
from app.recuperacao.tipos import Evidencia
from tests.recuperacao.conftest import criar_documento, criar_item, limpar_pontos_qdrant


def _indexar_e_construir_grafo(cliente, driver, documento, itens):
    indexar_e_persistir(documento.id_documento, itens, cliente)
    construir_grafo([(documento, itens)], driver)


def test_recuperar_traz_item_relevante_no_topo_com_evidencia_completa(db_session, qdrant_cliente, grafo_driver):
    documento = criar_documento(db_session, nome_arquivo="orq_1.pdf", departamento="DCC")
    item_relevante = criar_item(
        db_session, documento, numero_item="1", item_id_canonico="orq_relevante",
        texto="O conselho aprovou a reforma do laboratório de química por unanimidade.",
        tipo_desfecho="Aprovado", resultado_votacao="unanimidade", ato_emitido="RESOLUCAO_1_2025",
    )
    item_irrelevante = criar_item(
        db_session, documento, numero_item="2", item_id_canonico="orq_irrelevante",
        texto="O gato dormiu no sofá durante a tarde inteira.",
    )
    try:
        _indexar_e_construir_grafo(
            qdrant_cliente, grafo_driver, documento, [item_relevante, item_irrelevante]
        )

        resultado = recuperar(
            "aprovação da reforma do laboratório de química", db_session, qdrant_cliente, grafo_driver, k=2
        )

        assert len(resultado) >= 1
        primeiro = resultado[0]
        assert isinstance(primeiro, Evidencia)
        assert primeiro.item_id_canonico == "orq_relevante"
        assert primeiro.rank_final == 1
        assert primeiro.texto == item_relevante.texto
        assert primeiro.contexto_grafo["departamento"] == "DCC"
        assert set(primeiro.scores.keys()) == {"lexico", "vetorial", "grafo"}
    finally:
        limpar_pontos_qdrant(qdrant_cliente, documento.id_documento)


def test_recuperar_sem_correspondencia_retorna_lista_vazia(db_session, qdrant_cliente, grafo_driver):
    documento = criar_documento(db_session, nome_arquivo="orq_2.pdf")
    item = criar_item(db_session, documento, numero_item="1", texto="assunto completamente diferente.")
    try:
        _indexar_e_construir_grafo(qdrant_cliente, grafo_driver, documento, [item])

        resultado = recuperar(
            "zzzzz termo que nao existe em lugar nenhum yyyyy", db_session, qdrant_cliente, grafo_driver, k=5
        )

        # vetorial sempre devolve algo (busca por similaridade, nao correspondencia
        # exata) — a garantia real e que o pipeline nao quebra com pergunta sem
        # match lexico algum.
        assert isinstance(resultado, list)
    finally:
        limpar_pontos_qdrant(qdrant_cliente, documento.id_documento)


def test_recuperar_degrada_quando_camada_lexica_falha(db_session, qdrant_cliente, grafo_driver, monkeypatch):
    documento = criar_documento(db_session, nome_arquivo="orq_3.pdf")
    item = criar_item(
        db_session, documento, numero_item="1", item_id_canonico="orq_degrada_lexico",
        texto="O conselho aprovou a reforma do laboratório de química por unanimidade.",
    )
    try:
        _indexar_e_construir_grafo(qdrant_cliente, grafo_driver, documento, [item])

        def _levanta_erro(*args, **kwargs):
            raise RuntimeError("postgres indisponivel")

        monkeypatch.setattr("app.recuperacao.orquestrador.buscar_lexico", _levanta_erro)

        resultado = recuperar(
            "aprovação da reforma do laboratório de química", db_session, qdrant_cliente, grafo_driver, k=2
        )

        ids = [evidencia.item_id_canonico for evidencia in resultado]
        assert "orq_degrada_lexico" in ids
        evidencia = next(e for e in resultado if e.item_id_canonico == "orq_degrada_lexico")
        assert evidencia.scores["lexico"] is None
    finally:
        limpar_pontos_qdrant(qdrant_cliente, documento.id_documento)


def test_recuperar_degrada_lexico_apos_erro_sql_real_sem_quebrar_hidratacao(
    db_session, qdrant_cliente, grafo_driver, monkeypatch
):
    documento = criar_documento(db_session, nome_arquivo="orq_erro_sql.pdf")
    item = criar_item(
        db_session, documento, numero_item="1", item_id_canonico="orq_erro_sql_real",
        texto="O conselho aprovou a reforma do laboratório de química por unanimidade.",
    )
    try:
        _indexar_e_construir_grafo(qdrant_cliente, grafo_driver, documento, [item])

        def _lexico_com_erro_sql_real(pergunta, sessao):
            sessao.execute(text("SELECT * FROM tabela_inexistente_para_teste"))
            return []

        monkeypatch.setattr("app.recuperacao.orquestrador.buscar_lexico", _lexico_com_erro_sql_real)

        resultado = recuperar(
            "aprovação da reforma do laboratório de química", db_session, qdrant_cliente, grafo_driver, k=2
        )

        ids = [evidencia.item_id_canonico for evidencia in resultado]
        assert "orq_erro_sql_real" in ids
    finally:
        limpar_pontos_qdrant(qdrant_cliente, documento.id_documento)


def test_recuperar_sobrevive_a_dois_erros_sql_reais_na_mesma_chamada(
    db_session, qdrant_cliente, grafo_driver, monkeypatch
):
    documento = criar_documento(db_session, nome_arquivo="orq_erro_sql_duplo.pdf")
    item = criar_item(
        db_session, documento, numero_item="1", item_id_canonico="orq_erro_sql_duplo",
        texto="O conselho aprovou a reforma do laboratório de química por unanimidade.",
    )
    try:
        _indexar_e_construir_grafo(qdrant_cliente, grafo_driver, documento, [item])

        def _lexico_com_erro_sql_real(pergunta, sessao):
            sessao.execute(text("SELECT * FROM tabela_inexistente_para_teste"))
            return []

        def _hidratacao_com_erro_sql_real(sessao, ids_finais):
            sessao.execute(text("SELECT * FROM outra_tabela_inexistente_para_teste"))
            return {}

        monkeypatch.setattr("app.recuperacao.orquestrador.buscar_lexico", _lexico_com_erro_sql_real)
        monkeypatch.setattr(
            "app.recuperacao.orquestrador._buscar_itens_por_id", _hidratacao_com_erro_sql_real
        )

        resultado = recuperar(
            "aprovação da reforma do laboratório de química", db_session, qdrant_cliente, grafo_driver, k=2
        )

        assert resultado == []
        # a sessao precisa continuar utilizavel depois do recuperar() —
        # prova que os dois savepoints empilhados nao deixaram a transacao
        # externa do fixture (db_session) abortada.
        assert db_session.execute(text("SELECT 1")).scalar() == 1
    finally:
        limpar_pontos_qdrant(qdrant_cliente, documento.id_documento)


def test_recuperar_degrada_quando_expansao_de_grafo_falha(db_session, qdrant_cliente, grafo_driver, monkeypatch):
    documento = criar_documento(db_session, nome_arquivo="orq_4.pdf")
    item = criar_item(
        db_session, documento, numero_item="1", item_id_canonico="orq_degrada_grafo",
        texto="O conselho aprovou a reforma do laboratório de química por unanimidade.",
    )
    try:
        _indexar_e_construir_grafo(qdrant_cliente, grafo_driver, documento, [item])

        def _levanta_erro(*args, **kwargs):
            raise RuntimeError("neo4j indisponivel")

        monkeypatch.setattr("app.recuperacao.orquestrador.expandir_grafo", _levanta_erro)

        resultado = recuperar(
            "aprovação da reforma do laboratório de química", db_session, qdrant_cliente, grafo_driver, k=2
        )

        ids = [evidencia.item_id_canonico for evidencia in resultado]
        assert "orq_degrada_grafo" in ids
    finally:
        limpar_pontos_qdrant(qdrant_cliente, documento.id_documento)


def test_recuperar_rank_final_e_contiguo_quando_item_do_meio_nao_e_encontrado(
    db_session, qdrant_cliente, grafo_driver, monkeypatch
):
    documento = criar_documento(db_session, nome_arquivo="orq_6.pdf")
    item_a = criar_item(
        db_session, documento, numero_item="1", item_id_canonico="orq_rank_a", texto="texto a."
    )
    item_c = criar_item(
        db_session, documento, numero_item="3", item_id_canonico="orq_rank_c", texto="texto c."
    )
    try:
        _indexar_e_construir_grafo(qdrant_cliente, grafo_driver, documento, [item_a, item_c])

        monkeypatch.setattr(
            "app.recuperacao.orquestrador.pontuar_rrf",
            lambda *args, **kwargs: [
                {"item_id_canonico": i, "pontuacao": 0.0, "posicoes": {}}
                for i in ["orq_rank_a", "orq_rank_b", "orq_rank_c"]
            ],
        )
        monkeypatch.setattr(
            "app.recuperacao.orquestrador._buscar_itens_por_id",
            lambda sessao, ids_finais: {"orq_rank_a": item_a, "orq_rank_c": item_c},
        )

        resultado = recuperar("qualquer coisa", db_session, qdrant_cliente, grafo_driver, k=3)

        assert [e.item_id_canonico for e in resultado] == ["orq_rank_a", "orq_rank_c"]
        assert [e.rank_final for e in resultado] == [1, 2]
    finally:
        limpar_pontos_qdrant(qdrant_cliente, documento.id_documento)


def test_recuperar_degrada_quando_hidratacao_de_itens_falha(db_session, qdrant_cliente, grafo_driver, monkeypatch):
    documento = criar_documento(db_session, nome_arquivo="orq_5.pdf")
    item = criar_item(
        db_session, documento, numero_item="1", item_id_canonico="orq_degrada_hidratacao",
        texto="O conselho aprovou a reforma do laboratório de química por unanimidade.",
    )
    try:
        _indexar_e_construir_grafo(qdrant_cliente, grafo_driver, documento, [item])

        def _levanta_erro(*args, **kwargs):
            raise RuntimeError("postgres indisponivel")

        monkeypatch.setattr("app.recuperacao.orquestrador._buscar_itens_por_id", _levanta_erro)

        resultado = recuperar(
            "aprovação da reforma do laboratório de química", db_session, qdrant_cliente, grafo_driver, k=2
        )

        assert resultado == []
    finally:
        limpar_pontos_qdrant(qdrant_cliente, documento.id_documento)
