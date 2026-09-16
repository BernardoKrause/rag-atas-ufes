from datetime import date

from app.models.documento import Documento
from app.models.item_pauta import ItemPauta


def test_item_pauta_aceita_campos_de_enriquecimento_nulos(db_session):
    documento = Documento(
        nome_arquivo="x.pdf", url_origem="x.pdf", centro="CT", campus="Goiabeiras",
        tipo_orgao="B", orgao="CT", data_reuniao=date(2025, 1, 1), texto_limpo="texto",
    )
    db_session.add(documento)
    db_session.flush()

    item = ItemPauta(
        documento_id=documento.id_documento, item_id_canonico="1_PAUTA_1",
        secao="PAUTA", numero_item="1", texto="texto do item",
    )
    db_session.add(item)
    db_session.flush()

    assert item.assunto is None
    assert item.tipo_desfecho is None
    assert item.resultado_votacao is None
    assert item.encaminhamento is None
    assert item.ato_emitido is None
    assert item.departamento_origem is None


def test_item_pauta_aceita_campos_de_enriquecimento_preenchidos(db_session):
    documento = Documento(
        nome_arquivo="y.pdf", url_origem="y.pdf", centro="CT", campus="Goiabeiras",
        tipo_orgao="B", orgao="CT", data_reuniao=date(2025, 1, 1), texto_limpo="texto",
    )
    db_session.add(documento)
    db_session.flush()

    item = ItemPauta(
        documento_id=documento.id_documento, item_id_canonico="2_PAUTA_1",
        secao="PAUTA", numero_item="1", texto="texto do item",
        assunto="Homologação de licença", tipo_desfecho="Aprovado",
        resultado_votacao="unanimidade", encaminhamento="arquivamento",
        ato_emitido="RESOLUCAO_79_2025", departamento_origem="INFORMATICA",
    )
    db_session.add(item)
    db_session.flush()
    db_session.refresh(item)

    assert item.tipo_desfecho == "Aprovado"
    assert item.ato_emitido == "RESOLUCAO_79_2025"


def test_item_pauta_expoe_tsv_gerado_pelo_postgres(db_session):
    documento = Documento(
        nome_arquivo="z.pdf", url_origem="z.pdf", centro="CT", campus="Goiabeiras",
        tipo_orgao="B", orgao="CT", data_reuniao=date(2025, 1, 1), texto_limpo="texto",
    )
    db_session.add(documento)
    db_session.flush()

    item = ItemPauta(
        documento_id=documento.id_documento, item_id_canonico="3_PAUTA_1",
        secao="PAUTA", numero_item="1", texto="aprovação da reforma do laboratório",
    )
    db_session.add(item)
    db_session.flush()
    db_session.refresh(item)

    assert item.tsv is not None
    assert "aprov" in item.tsv
