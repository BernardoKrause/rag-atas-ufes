from app.ingestion.indexador import indexar_e_persistir
from app.recuperacao.lexico import buscar_lexico
from app.recuperacao.orquestrador import recuperar
from app.recuperacao.setor import identificar_orgao, listar_orgaos
from app.recuperacao.tipos import Hit
from app.recuperacao.vetorial import buscar_vetorial
from tests.recuperacao.conftest import criar_documento, criar_item, limpar_pontos_qdrant

TEXTO = "O conselho aprovou a reforma do laboratório de química por unanimidade."


def _dois_orgaos(db_session):
    deal = criar_documento(db_session, nome_arquivo="setor_deal.pdf", orgao="CCAE_DEAL")
    dpv = criar_documento(db_session, nome_arquivo="setor_dpv.pdf", orgao="CCAE_DPV")
    item_deal = criar_item(db_session, deal, item_id_canonico="setor_deal", texto=TEXTO)
    item_dpv = criar_item(db_session, dpv, item_id_canonico="setor_dpv", texto=TEXTO)
    return (deal, item_deal), (dpv, item_dpv)


def test_identifica_o_orgao_citado_na_pergunta(db_session):
    _dois_orgaos(db_session)
    criar_documento(db_session, nome_arquivo="setor_cchn.pdf", orgao="CCHN_CamaraLocal_Graduacao")

    assert identificar_orgao("Qual foi a decisão sobre X no setor CCAE / DEAL?", db_session) == "CCAE_DEAL"
    assert identificar_orgao("E sobre Y no setor CCHN / CAMARALOCAL / GRADUACAO?", db_session) == (
        "CCHN_CamaraLocal_Graduacao"
    )


def test_sem_setor_ou_setor_desconhecido_nao_filtra(db_session):
    _dois_orgaos(db_session)

    assert identificar_orgao("Qual foi a decisão sobre X?", db_session) is None
    assert identificar_orgao("Qual foi a decisão sobre X no setor CT / XYZ?", db_session) is None


def test_lexico_filtra_pelo_orgao_sem_mudar_a_pontuacao(db_session):
    _dois_orgaos(db_session)

    todos = {hit.item_id_canonico: hit.score for hit in buscar_lexico("reforma do laboratório", db_session)}
    filtrados = buscar_lexico("reforma do laboratório", db_session, orgao="CCAE_DEAL")

    assert [hit.item_id_canonico for hit in filtrados] == ["setor_deal"]
    assert filtrados[0].score == todos["setor_deal"]


def test_vetorial_filtra_pelos_documentos_do_orgao(db_session, qdrant_cliente):
    (deal, item_deal), (dpv, item_dpv) = _dois_orgaos(db_session)
    try:
        indexar_e_persistir(deal.id_documento, [item_deal], qdrant_cliente)
        indexar_e_persistir(dpv.id_documento, [item_dpv], qdrant_cliente)

        resultados = buscar_vetorial("reforma do laboratório", qdrant_cliente, documentos=[deal.id_documento])

        assert [hit.item_id_canonico for hit in resultados] == ["setor_deal"]
    finally:
        limpar_pontos_qdrant(qdrant_cliente, deal.id_documento)
        limpar_pontos_qdrant(qdrant_cliente, dpv.id_documento)


def test_recuperar_so_traz_itens_do_setor_citado(db_session, qdrant_cliente, grafo_driver, monkeypatch):
    (deal, item_deal), (dpv, item_dpv) = _dois_orgaos(db_session)
    monkeypatch.setattr(
        "app.recuperacao.orquestrador.expandir_grafo", lambda ancoras, driver: [Hit("setor_dpv", 1)]
    )
    try:
        indexar_e_persistir(deal.id_documento, [item_deal], qdrant_cliente)
        indexar_e_persistir(dpv.id_documento, [item_dpv], qdrant_cliente)

        com_setor = recuperar(
            "reforma do laboratório no setor CCAE / DEAL?", db_session, qdrant_cliente, grafo_driver
        )
        sem_setor = recuperar("reforma do laboratório?", db_session, qdrant_cliente, grafo_driver)

        assert [e.item_id_canonico for e in com_setor] == ["setor_deal"]
        assert {e.item_id_canonico for e in sem_setor} == {"setor_deal", "setor_dpv"}
    finally:
        limpar_pontos_qdrant(qdrant_cliente, deal.id_documento)
        limpar_pontos_qdrant(qdrant_cliente, dpv.id_documento)


def test_orgao_selecionado_prevalece_sobre_o_setor_da_pergunta(db_session, qdrant_cliente, grafo_driver, monkeypatch):
    (deal, item_deal), (dpv, item_dpv) = _dois_orgaos(db_session)
    monkeypatch.setattr("app.recuperacao.orquestrador.expandir_grafo", lambda ancoras, driver: [])
    try:
        indexar_e_persistir(deal.id_documento, [item_deal], qdrant_cliente)
        indexar_e_persistir(dpv.id_documento, [item_dpv], qdrant_cliente)
        registro = {}

        selecionado = recuperar(
            "reforma do laboratório no setor CCAE / DEAL?", db_session, qdrant_cliente, grafo_driver,
            orgao="CCAE_DPV", registro=registro,
        )

        assert [e.item_id_canonico for e in selecionado] == ["setor_dpv"]
        assert registro["orgao"] == "CCAE_DPV"
        assert registro["origem_orgao"] == "selecao"
    finally:
        limpar_pontos_qdrant(qdrant_cliente, deal.id_documento)
        limpar_pontos_qdrant(qdrant_cliente, dpv.id_documento)


def test_listar_orgaos_conta_as_atas_de_cada_orgao(db_session):
    _dois_orgaos(db_session)
    criar_documento(db_session, nome_arquivo="setor_deal_2.pdf", orgao="CCAE_DEAL")

    contagem = dict(listar_orgaos(db_session))

    assert contagem["CCAE_DEAL"] == 2
    assert contagem["CCAE_DPV"] == 1
