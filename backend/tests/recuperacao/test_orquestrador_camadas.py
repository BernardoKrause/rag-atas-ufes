import pytest

from app.recuperacao import orquestrador
from app.recuperacao.orquestrador import CAMADAS_TODAS, recuperar
from app.recuperacao.tipos import Hit
from tests.recuperacao.conftest import criar_documento, criar_item


@pytest.fixture()
def camadas_falsas(db_session, monkeypatch):
    documento = criar_documento(db_session, nome_arquivo="camadas_1.pdf")
    criar_item(db_session, documento, numero_item="1", item_id_canonico="cam_lex")
    criar_item(db_session, documento, numero_item="2", item_id_canonico="cam_vet")
    criar_item(db_session, documento, numero_item="3", item_id_canonico="cam_grafo")
    chamadas = []

    def lexico(pergunta, sessao, orgao=None):
        chamadas.append("lexico")
        return [Hit("cam_lex", 1)]

    def vetorial(pergunta, cliente, documentos=None):
        chamadas.append("vetorial")
        return [Hit("cam_vet", 1)]

    def grafo(ancoras, driver):
        chamadas.append("grafo")
        return [Hit("cam_grafo", 1)]

    def contextos(ids, driver):
        chamadas.append("contexto_grafo")
        return {item_id: {"departamento": "X"} for item_id in ids}

    monkeypatch.setattr(orquestrador, "buscar_lexico", lexico)
    monkeypatch.setattr(orquestrador, "buscar_vetorial", vetorial)
    monkeypatch.setattr(orquestrador, "expandir_grafo", grafo)
    monkeypatch.setattr(orquestrador, "obter_contextos_grafo", contextos)
    return chamadas


def _ids(evidencias):
    return {e.item_id_canonico for e in evidencias}


def test_padrao_usa_as_tres_camadas(db_session, camadas_falsas):
    resultado = recuperar("p", db_session, None, None)

    assert _ids(resultado) == {"cam_lex", "cam_vet", "cam_grafo"}
    assert camadas_falsas == ["lexico", "vetorial", "grafo", "contexto_grafo"]
    assert CAMADAS_TODAS == frozenset({"lexico", "vetorial", "grafo"})


def test_sem_grafo_nao_expande_nem_traz_contexto_do_grafo(db_session, camadas_falsas):
    resultado = recuperar("p", db_session, None, None, camadas=frozenset({"lexico", "vetorial"}))

    assert _ids(resultado) == {"cam_lex", "cam_vet"}
    assert camadas_falsas == ["lexico", "vetorial"]
    assert all(e.contexto_grafo == {} for e in resultado)


def test_so_lexico(db_session, camadas_falsas):
    resultado = recuperar("p", db_session, None, None, camadas=frozenset({"lexico"}))

    assert _ids(resultado) == {"cam_lex"}
    assert camadas_falsas == ["lexico"]


def test_so_vetorial(db_session, camadas_falsas):
    resultado = recuperar("p", db_session, None, None, camadas=frozenset({"vetorial"}))

    assert _ids(resultado) == {"cam_vet"}
    assert camadas_falsas == ["vetorial"]


@pytest.mark.parametrize("camadas", [frozenset({"grafo"}), frozenset({"lexico", "bm25"}), frozenset()])
def test_camadas_invalidas_levantam_value_error(db_session, camadas):
    with pytest.raises(ValueError):
        recuperar("p", db_session, None, None, camadas=camadas)
