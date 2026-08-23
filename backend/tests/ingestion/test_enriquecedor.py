from datetime import date

from app.ingestion.enriquecedor import CamposEnriquecidos, enriquecer_e_persistir
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta


def test_enriquecer_e_persistir_preenche_campos_do_item(db_session, monkeypatch):
    import app.ingestion.enriquecedor as mod
    monkeypatch.setitem(
        mod.CONFIG_ENRIQUECEDOR, ("B", "CT"),
        lambda texto, data_reuniao: CamposEnriquecidos(
            assunto="assunto teste", tipo_desfecho="Aprovado", resultado_votacao="unanimidade",
            encaminhamento=None, ato_emitido=None, departamento_origem="INFORMATICA",
        ),
    )

    documento = Documento(
        nome_arquivo="x.pdf", url_origem="x.pdf", centro="CT", campus="Goiabeiras",
        tipo_orgao="B", orgao="CT", data_reuniao=date(2025, 1, 1), texto_limpo="texto",
    )
    db_session.add(documento)
    db_session.flush()
    item = ItemPauta(
        documento_id=documento.id_documento, item_id_canonico="1_PAUTA_1",
        secao="PAUTA", numero_item="1", texto="PAUTA 1: texto do item",
    )
    db_session.add(item)
    db_session.flush()

    enriquecer_e_persistir(documento, [item], db_session)

    assert item.assunto == "assunto teste"
    assert item.tipo_desfecho == "Aprovado"
    assert item.departamento_origem == "INFORMATICA"


def test_enriquecer_e_persistir_e_idempotente(db_session, monkeypatch):
    import app.ingestion.enriquecedor as mod
    chamadas = []
    def _fake(texto, data_reuniao):
        chamadas.append(texto)
        return CamposEnriquecidos(None, "Aprovado", None, None, None, None)
    monkeypatch.setitem(mod.CONFIG_ENRIQUECEDOR, ("B", "CT"), _fake)

    documento = Documento(
        nome_arquivo="y.pdf", url_origem="y.pdf", centro="CT", campus="Goiabeiras",
        tipo_orgao="B", orgao="CT", data_reuniao=date(2025, 1, 1), texto_limpo="texto",
    )
    db_session.add(documento)
    db_session.flush()
    item = ItemPauta(
        documento_id=documento.id_documento, item_id_canonico="2_PAUTA_1",
        secao="PAUTA", numero_item="1", texto="PAUTA 1: texto do item",
    )
    db_session.add(item)
    db_session.flush()

    enriquecer_e_persistir(documento, [item], db_session)
    enriquecer_e_persistir(documento, [item], db_session)

    assert len(chamadas) == 2
    assert item.tipo_desfecho == "Aprovado"


def test_extrair_corpo_sem_marcador_ct():
    from app.ingestion.enriquecedor import extrair_corpo_sem_marcador
    texto = 'PAUTA 2: Processo digital nº 23068.007249/2025-23 - homologação - Departamento de Informática - Interrupção. Decisão: Homologado(a).'
    corpo = extrair_corpo_sem_marcador("PAUTA", texto)
    assert corpo.startswith("Processo digital")


def test_extrair_corpo_sem_marcador_pontilhado():
    from app.ingestion.enriquecedor import extrair_corpo_sem_marcador
    texto = '4.3. Apreciação com sugestões para aprimoramento da proposta. Decisão: Aprovado.'
    corpo = extrair_corpo_sem_marcador("INFORMES", texto)
    assert corpo.startswith("Apreciação")
