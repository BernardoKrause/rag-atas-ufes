from datetime import date

import pytest

from app.grafo.cliente import obter_driver
from app.grafo.construtor import limpar_grafo
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta


@pytest.fixture()
def grafo_driver():
    driver = obter_driver()
    limpar_grafo(driver)
    yield driver
    limpar_grafo(driver)
    driver.close()


def criar_documento(sessao, **overrides):
    base = dict(
        nome_arquivo="teste_recuperacao.pdf", url_origem="http://exemplo", centro="CT",
        campus="Goiabeiras", tipo_orgao="B", orgao="CT_DB", data_reuniao=date(2025, 1, 1),
        texto_limpo="texto",
    )
    base.update(overrides)
    documento = Documento(**base)
    sessao.add(documento)
    sessao.flush()
    return documento


def criar_item(sessao, documento, **overrides):
    base = dict(
        documento_id=documento.id_documento, secao="PAUTA", numero_item="1",
        ocorrencia_indice=0, fragmento_indice=0, texto="texto do item de teste.",
    )
    base.update(overrides)
    base.setdefault("item_id_canonico", f"{documento.id_documento}_pauta_{base['numero_item']}")
    item = ItemPauta(**base)
    sessao.add(item)
    sessao.flush()
    return item


@pytest.fixture(autouse=True)
def _limpar_tabelas_teste(db_session):
    from sqlalchemy import text
    db_session.execute(text("DELETE FROM itens_pauta"))
    db_session.execute(text("DELETE FROM documentos"))
    db_session.flush()
    yield
