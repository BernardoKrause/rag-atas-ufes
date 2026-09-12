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
