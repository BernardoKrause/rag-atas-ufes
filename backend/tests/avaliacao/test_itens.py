from datetime import date

from app.avaliacao.itens import descrever_itens, mapa_item_logico
from tests.recuperacao.conftest import criar_documento, criar_item


def test_mapa_aponta_fragmentos_para_o_item_logico(db_session):
    documento = criar_documento(db_session, nome_arquivo="itens_1.pdf")
    criar_item(db_session, documento, numero_item="1", item_id_canonico="itn_1")
    criar_item(
        db_session, documento, numero_item="1", fragmento_indice=1, item_id_canonico="itn_1_F1"
    )
    criar_item(db_session, documento, numero_item="2", item_id_canonico="itn_2")

    mapa = mapa_item_logico(db_session)

    assert mapa["itn_1"] == "itn_1"
    assert mapa["itn_1_F1"] == "itn_1"
    assert mapa["itn_2"] == "itn_2"


def test_descrever_itens_traz_metadados_da_ata(db_session):
    documento = criar_documento(
        db_session, nome_arquivo="itens_2.pdf", orgao="CCAE_DER", data_reuniao=date(2025, 4, 25),
        numero_reuniao=3,
    )
    criar_item(
        db_session, documento, numero_item="1", item_id_canonico="itn_desc", assunto="Afastamento",
        texto="Aprovado o afastamento.", pagina_inicio=2,
    )

    descricao = descrever_itens(db_session, ["itn_desc"])["itn_desc"]

    assert descricao == {
        "orgao": "CCAE_DER", "data_reuniao": "2025-04-25", "numero_reuniao": 3,
        "assunto": "Afastamento", "texto": "Aprovado o afastamento.", "pagina_inicio": 2,
    }
