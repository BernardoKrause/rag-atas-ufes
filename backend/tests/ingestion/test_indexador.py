import uuid
from datetime import date

from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue

from app.core.config import settings
from app.ingestion.indexador import (
    DIMENSAO_EMBEDDING,
    carregar_modelo,
    gerar_embedding,
    gerar_janelas,
    gerar_point_id,
    garantir_collection,
    indexar_e_persistir,
    tokenizar_texto,
)
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta


def _criar_documento(sessao, **overrides):
    base = dict(
        nome_arquivo="teste_indexador.pdf", url_origem="http://exemplo", centro="CCENS",
        campus="Alegre", tipo_orgao="A", orgao="CCENS_DB", data_reuniao=date(2025, 1, 1),
        texto_limpo="texto", paginas_offsets=[0],
    )
    base.update(overrides)
    documento = Documento(**base)
    sessao.add(documento)
    sessao.flush()
    return documento


def _criar_item(sessao, documento, **overrides):
    base = dict(
        documento_id=documento.id_documento, secao="PAUTA", numero_item="1",
        ocorrencia_indice=0, fragmento_indice=0, texto="texto do item de teste sobre a pauta discutida.",
    )
    base.update(overrides)
    base.setdefault("item_id_canonico", f"{documento.id_documento}_pauta_{base['numero_item']}")
    item = ItemPauta(**base)
    sessao.add(item)
    sessao.flush()
    return item


def _limpar_pontos_do_documento(cliente, documento_id):
    cliente.delete(
        collection_name=settings.qdrant_collection,
        points_selector=Filter(must=[FieldCondition(key="documento_id", match=MatchValue(value=documento_id))]),
    )


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


def test_garantir_collection_cria_collection_com_config_correta(qdrant_cliente, monkeypatch):
    nome_temporario = f"itens_pauta_teste_{uuid.uuid4().hex}"
    monkeypatch.setattr(settings, "qdrant_collection", nome_temporario)

    try:
        assert not qdrant_cliente.collection_exists(nome_temporario)

        garantir_collection(qdrant_cliente)

        assert qdrant_cliente.collection_exists(nome_temporario)
        info = qdrant_cliente.get_collection(nome_temporario)
        assert info.config.params.vectors.size == DIMENSAO_EMBEDDING
        assert info.config.params.vectors.distance == Distance.COSINE
    finally:
        qdrant_cliente.delete_collection(nome_temporario)


def test_garantir_collection_e_idempotente_quando_ja_existe(qdrant_cliente):
    garantir_collection(qdrant_cliente)

    garantir_collection(qdrant_cliente)  # nao deve levantar erro

    assert qdrant_cliente.collection_exists(settings.qdrant_collection)


def test_gerar_embedding_retorna_vetor_normalizado_de_768_dimensoes():
    tokenizer, modelo = carregar_modelo()
    token_ids = tokenizar_texto(tokenizer, "O conselho aprovou a pauta por unanimidade.")

    embedding = gerar_embedding(tokenizer, modelo, token_ids)

    assert len(embedding) == 768
    norma = sum(v * v for v in embedding) ** 0.5
    assert abs(norma - 1.0) < 1e-4


def test_gerar_embedding_e_deterministico():
    tokenizer, modelo = carregar_modelo()
    token_ids = tokenizar_texto(tokenizer, "Texto de teste.")

    e1 = gerar_embedding(tokenizer, modelo, token_ids)
    e2 = gerar_embedding(tokenizer, modelo, token_ids)

    assert e1 == e2


def test_gerar_embedding_captura_similaridade_semantica():
    tokenizer, modelo = carregar_modelo()

    a = gerar_embedding(tokenizer, modelo, tokenizar_texto(tokenizer, "O conselho aprovou a pauta por unanimidade."))
    a_parafrase = gerar_embedding(
        tokenizer, modelo, tokenizar_texto(tokenizer, "A pauta foi aprovada pelo conselho de forma unanime.")
    )
    b_nao_relacionado = gerar_embedding(
        tokenizer, modelo, tokenizar_texto(tokenizer, "O gato dormiu no sofa durante a tarde inteira.")
    )

    def cosseno(x, y):
        produto = sum(xi * yi for xi, yi in zip(x, y))
        norma_x = sum(xi * xi for xi in x) ** 0.5
        norma_y = sum(yi * yi for yi in y) ** 0.5
        return produto / (norma_x * norma_y)

    similaridade_parafrase = cosseno(a, a_parafrase)
    similaridade_nao_relacionado = cosseno(a, b_nao_relacionado)

    assert similaridade_parafrase > similaridade_nao_relacionado


def test_tokenizar_texto_nao_inclui_tokens_especiais():
    tokenizer, _ = carregar_modelo()

    token_ids = tokenizar_texto(tokenizer, "teste")

    assert tokenizer.cls_token_id not in token_ids
    assert tokenizer.sep_token_id not in token_ids


def test_indexar_e_persistir_cria_um_ponto_por_janela(db_session, qdrant_cliente):
    documento = _criar_documento(db_session)
    item = _criar_item(db_session, documento, numero_item="1", item_id_canonico="idx_teste_1")

    try:
        total = indexar_e_persistir(documento.id_documento, [item], qdrant_cliente)

        assert total == 1
        resultado, _ = qdrant_cliente.scroll(
            collection_name=settings.qdrant_collection,
            scroll_filter=Filter(must=[FieldCondition(key="item_id_canonico", match=MatchValue(value="idx_teste_1"))]),
        )
        assert len(resultado) == 1
        assert resultado[0].payload["janela_indice"] == 0
        assert resultado[0].payload["documento_id"] == documento.id_documento
    finally:
        _limpar_pontos_do_documento(qdrant_cliente, documento.id_documento)


def test_indexar_e_persistir_upsert_sobrescreve_quando_texto_muda(db_session, qdrant_cliente):
    documento = _criar_documento(db_session, nome_arquivo="upsert.pdf")
    item = _criar_item(db_session, documento, numero_item="1", item_id_canonico="idx_teste_upsert")

    try:
        indexar_e_persistir(documento.id_documento, [item], qdrant_cliente)
        item.texto = "texto atualizado do mesmo item, ainda cabe em uma unica janela de tokens."
        db_session.flush()
        total = indexar_e_persistir(documento.id_documento, [item], qdrant_cliente)

        assert total == 1
        resultado, _ = qdrant_cliente.scroll(
            collection_name=settings.qdrant_collection,
            scroll_filter=Filter(must=[FieldCondition(key="item_id_canonico", match=MatchValue(value="idx_teste_upsert"))]),
        )
        assert len(resultado) == 1  # nao duplicou
    finally:
        _limpar_pontos_do_documento(qdrant_cliente, documento.id_documento)


def test_indexar_e_persistir_gera_um_ponto_por_janela_em_texto_longo(db_session, qdrant_cliente):
    frase = (
        "O conselho universitario discutiu a pauta e aprovou por unanimidade "
        "a proposta apresentada pelo relator. "
    )
    texto_longo = frase * 15
    documento = _criar_documento(db_session, nome_arquivo="janelas_multiplas.pdf")
    item = _criar_item(
        db_session, documento, numero_item="1", item_id_canonico="idx_teste_multi_janela", texto=texto_longo
    )

    try:
        total = indexar_e_persistir(documento.id_documento, [item], qdrant_cliente)

        tokenizer, _ = carregar_modelo()
        janelas_esperadas = gerar_janelas(tokenizar_texto(tokenizer, texto_longo))
        assert total == len(janelas_esperadas)
        assert total > 1  # confirma que o texto de fato exercita o caminho multi-janela

        resultado, _ = qdrant_cliente.scroll(
            collection_name=settings.qdrant_collection,
            scroll_filter=Filter(
                must=[FieldCondition(key="item_id_canonico", match=MatchValue(value="idx_teste_multi_janela"))]
            ),
            limit=len(janelas_esperadas),
        )
        indices_presentes = sorted(ponto.payload["janela_indice"] for ponto in resultado)
        assert indices_presentes == list(range(len(janelas_esperadas)))
        assert len({ponto.id for ponto in resultado}) == len(resultado)

        ponto_janela_1 = next(p for p in resultado if p.payload["janela_indice"] == 1)
        assert (ponto_janela_1.payload["offset_inicio"], ponto_janela_1.payload["offset_fim"]) == (100, 220)
    finally:
        _limpar_pontos_do_documento(qdrant_cliente, documento.id_documento)


def test_indexar_e_persistir_remove_pontos_orfaos_na_reindexacao(db_session, qdrant_cliente):
    documento = _criar_documento(db_session, nome_arquivo="reindex.pdf")
    item_a = _criar_item(db_session, documento, numero_item="1", item_id_canonico="idx_orfao_a")
    item_b = _criar_item(db_session, documento, numero_item="2", item_id_canonico="idx_orfao_b")
    try:
        indexar_e_persistir(documento.id_documento, [item_a, item_b], qdrant_cliente)

        # simula re-segmentacao: item_b sumiu, item_c e novo
        item_c = _criar_item(db_session, documento, numero_item="3", item_id_canonico="idx_orfao_c")
        indexar_e_persistir(documento.id_documento, [item_a, item_c], qdrant_cliente)

        resultado, _ = qdrant_cliente.scroll(
            collection_name=settings.qdrant_collection,
            scroll_filter=Filter(must=[FieldCondition(key="documento_id", match=MatchValue(value=documento.id_documento))]),
        )
        ids_presentes = {ponto.payload["item_id_canonico"] for ponto in resultado}
        assert ids_presentes == {"idx_orfao_a", "idx_orfao_c"}
    finally:
        _limpar_pontos_do_documento(qdrant_cliente, documento.id_documento)


def test_suite_usa_a_collection_de_teste_e_nao_a_de_desenvolvimento(qdrant_cliente):
    assert settings.qdrant_collection_teste != "itens_pauta"
    garantir_collection(qdrant_cliente)
    assert qdrant_cliente.collection_exists(settings.qdrant_collection_teste)
