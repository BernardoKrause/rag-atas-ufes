import uuid

from qdrant_client.models import Distance

from app.ingestion.indexador import COLLECTION, DIMENSAO_EMBEDDING, gerar_janelas, gerar_point_id, garantir_collection


def test_gerar_janelas_texto_menor_que_janela_gera_uma_unica_janela():
    token_ids = list(range(50))

    janelas = gerar_janelas(token_ids)

    assert len(janelas) == 1
    assert janelas[0].indice == 0
    assert janelas[0].offset_inicio == 0
    assert janelas[0].offset_fim == 50
    assert janelas[0].token_ids == token_ids


def test_gerar_janelas_aplica_sobreposicao_entre_janelas_consecutivas():
    token_ids = list(range(250))

    janelas = gerar_janelas(token_ids)

    assert [j.indice for j in janelas] == [0, 1, 2]
    assert (janelas[0].offset_inicio, janelas[0].offset_fim) == (0, 120)
    assert (janelas[1].offset_inicio, janelas[1].offset_fim) == (100, 220)
    assert (janelas[2].offset_inicio, janelas[2].offset_fim) == (200, 250)
    assert janelas[1].token_ids == token_ids[100:220]


def test_gerar_janelas_lista_vazia_nao_gera_janelas():
    assert gerar_janelas([]) == []


def test_gerar_point_id_e_deterministico_e_valido():
    id1 = gerar_point_id("42_pauta_3.2", 0)
    id2 = gerar_point_id("42_pauta_3.2", 0)

    assert id1 == id2
    uuid.UUID(id1)  # nao levanta ValueError


def test_gerar_point_id_muda_com_janela_indice_diferente():
    assert gerar_point_id("42_pauta_3.2", 0) != gerar_point_id("42_pauta_3.2", 1)


def test_gerar_point_id_muda_com_item_id_canonico_diferente():
    assert gerar_point_id("42_pauta_3.2", 0) != gerar_point_id("42_pauta_3.3", 0)


def test_garantir_collection_cria_collection_com_config_correta(qdrant_cliente):
    qdrant_cliente.delete_collection(COLLECTION)
    assert not qdrant_cliente.collection_exists(COLLECTION)

    garantir_collection(qdrant_cliente)

    assert qdrant_cliente.collection_exists(COLLECTION)
    info = qdrant_cliente.get_collection(COLLECTION)
    assert info.config.params.vectors.size == DIMENSAO_EMBEDDING
    assert info.config.params.vectors.distance == Distance.COSINE


def test_garantir_collection_e_idempotente_quando_ja_existe(qdrant_cliente):
    garantir_collection(qdrant_cliente)

    garantir_collection(qdrant_cliente)  # nao deve levantar erro

    assert qdrant_cliente.collection_exists(COLLECTION)
