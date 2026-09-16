from app.ingestion.indexador import indexar_e_persistir
from app.recuperacao.vetorial import buscar_vetorial
from tests.recuperacao.conftest import criar_documento, criar_item, limpar_pontos_qdrant


def test_buscar_vetorial_ranqueia_por_similaridade_semantica(db_session, qdrant_cliente):
    documento = criar_documento(db_session, nome_arquivo="vetorial.pdf")
    item_relevante = criar_item(
        db_session, documento, numero_item="1", item_id_canonico="vet_relevante",
        texto="O conselho aprovou a reforma do laboratório de química por unanimidade.",
    )
    item_irrelevante = criar_item(
        db_session, documento, numero_item="2", item_id_canonico="vet_irrelevante",
        texto="O gato dormiu no sofá durante a tarde inteira.",
    )
    try:
        indexar_e_persistir(documento.id_documento, [item_relevante, item_irrelevante], qdrant_cliente)

        resultados = buscar_vetorial("aprovação da reforma do laboratório", qdrant_cliente)

        ids = [hit.item_id_canonico for hit in resultados]
        assert ids[0] == item_relevante.item_id_canonico
        assert resultados[0].rank == 1
    finally:
        limpar_pontos_qdrant(qdrant_cliente, documento.id_documento)


def test_buscar_vetorial_colapsa_multiplas_janelas_do_mesmo_item(db_session, qdrant_cliente):
    frase = "O conselho universitário discutiu e aprovou a proposta apresentada pelo relator. "
    documento = criar_documento(db_session, nome_arquivo="vetorial_multi_janela.pdf")
    item = criar_item(
        db_session, documento, numero_item="1", item_id_canonico="vet_multi_janela", texto=frase * 15,
    )
    try:
        indexar_e_persistir(documento.id_documento, [item], qdrant_cliente)

        resultados = buscar_vetorial("proposta aprovada pelo conselho", qdrant_cliente)

        ids = [hit.item_id_canonico for hit in resultados]
        assert ids.count("vet_multi_janela") == 1
    finally:
        limpar_pontos_qdrant(qdrant_cliente, documento.id_documento)
