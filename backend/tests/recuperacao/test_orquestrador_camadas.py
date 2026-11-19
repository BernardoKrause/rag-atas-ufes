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


def test_padrao_usa_todas_as_camadas(db_session, camadas_falsas):
    resultado = recuperar("p", db_session, None, None)

    assert _ids(resultado) == {"cam_lex", "cam_vet", "cam_grafo"}
    assert camadas_falsas == ["lexico", "vetorial", "grafo", "contexto_grafo"]
    assert CAMADAS_TODAS == frozenset({"lexico", "vetorial", "grafo", "campos_grafo"})


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


def test_expansao_sem_campos_do_grafo(db_session, camadas_falsas):
    resultado = recuperar("p", db_session, None, None, camadas=frozenset({"lexico", "vetorial", "grafo"}))

    assert _ids(resultado) == {"cam_lex", "cam_vet", "cam_grafo"}
    assert camadas_falsas == ["lexico", "vetorial", "grafo"]
    assert all(e.contexto_grafo == {} for e in resultado)


def test_campos_do_grafo_sem_expansao(db_session, camadas_falsas):
    resultado = recuperar(
        "p", db_session, None, None, camadas=frozenset({"lexico", "vetorial", "campos_grafo"})
    )

    assert _ids(resultado) == {"cam_lex", "cam_vet"}
    assert camadas_falsas == ["lexico", "vetorial", "contexto_grafo"]
    assert all(e.contexto_grafo == {"departamento": "X"} for e in resultado)


def test_registro_guarda_buscas_fusao_e_caminhos(db_session, camadas_falsas, monkeypatch):
    monkeypatch.setattr(
        orquestrador, "rastrear_expansao",
        lambda ancoras, driver: [{"ancora": "cam_lex", "item_id_canonico": "cam_grafo", "relacao": "TRATA_DE"}],
    )
    registro = {}

    recuperar("p", db_session, None, None, registro=registro)

    assert [h["item_id_canonico"] for h in registro["lexico"]] == ["cam_lex"]
    assert [h["item_id_canonico"] for h in registro["vetorial"]] == ["cam_vet"]
    assert [h["item_id_canonico"] for h in registro["ancoras"]] == ["cam_lex", "cam_vet"]
    assert [h["item_id_canonico"] for h in registro["grafo"]] == ["cam_grafo"]
    assert registro["caminhos_grafo"][0]["relacao"] == "TRATA_DE"
    assert {linha["item_id_canonico"] for linha in registro["fusao"]} == {"cam_lex", "cam_vet", "cam_grafo"}
    assert all(linha["pontuacao"] == pytest.approx(1 / 61) for linha in registro["fusao"])
    assert registro["fusao"][0]["posicoes"] == {"lexico": 1}
    assert registro["ids_finais"] == [linha["item_id_canonico"] for linha in registro["fusao"]]
    assert set(registro["contextos_grafo"]) == {"cam_lex", "cam_vet", "cam_grafo"}
    assert registro["falhas"] == []


def test_registro_anota_camada_que_falhou(db_session, camadas_falsas, monkeypatch):
    def vetorial_quebrado(pergunta, cliente, documentos=None):
        raise RuntimeError("qdrant fora")

    monkeypatch.setattr(orquestrador, "buscar_vetorial", vetorial_quebrado)
    registro = {}

    recuperar("p", db_session, None, None, camadas=frozenset({"lexico", "vetorial"}), registro=registro)

    assert registro["falhas"] == ["vetorial"]
    assert registro["vetorial"] == []


@pytest.mark.parametrize("camadas", [frozenset({"grafo"}), frozenset({"campos_grafo"}), frozenset({"lexico", "bm25"}), frozenset()])
def test_camadas_invalidas_levantam_value_error(db_session, camadas):
    with pytest.raises(ValueError):
        recuperar("p", db_session, None, None, camadas=camadas)
