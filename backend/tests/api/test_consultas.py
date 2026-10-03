import pytest

from app.geracao.prompt import FRASE_ABSTENCAO
from app.recuperacao.tipos import Evidencia
from tests.recuperacao.conftest import criar_documento, criar_item


def _evidencia(item, rank):
    return Evidencia(
        item_id_canonico=item.item_id_canonico, texto=item.texto, contexto_grafo={},
        rank_final=rank, scores={"lexico": None, "vetorial": None, "grafo": None},
    )


@pytest.fixture()
def perguntas_recebidas(db_session, monkeypatch):
    documento = criar_documento(db_session, nome_arquivo="api_1.pdf", orgao="CT_DB")
    item = criar_item(
        db_session, documento, numero_item="4", texto="O conselho aprovou o calendário.",
        pagina_inicio=2,
    )
    recebidas = []

    def recuperar_falso(pergunta, *args, **kwargs):
        recebidas.append(pergunta)
        return [_evidencia(item, 1)]

    monkeypatch.setattr("app.geracao.respondedor.recuperar", recuperar_falso)
    return recebidas, item


def test_consulta_devolve_resposta_com_fonte_completa(
    cliente_api, llm_falso, perguntas_recebidas
):
    recebidas, item = perguntas_recebidas
    llm_falso.texto = "O calendário foi aprovado [1]."

    resposta = cliente_api.post("/consultas", json={"pergunta": "  O calendário foi aprovado?  "})

    assert resposta.status_code == 200
    assert recebidas == ["O calendário foi aprovado?"]
    assert resposta.json() == {
        "texto": "O calendário foi aprovado [1].",
        "abstencao": False,
        "fontes": [
            {
                "numero": 1,
                "item_id_canonico": item.item_id_canonico,
                "rotulo": "Ata CT_DB, 01/01/2025, pauta, item 4, p. 2",
                "trecho": "O conselho aprovou o calendário.",
                "pagina": 2,
                "url_pdf": f"/documentos/{item.documento_id}/pdf",
            }
        ],
    }


def test_consulta_com_abstencao_do_llm(cliente_api, llm_falso, perguntas_recebidas):
    llm_falso.texto = FRASE_ABSTENCAO

    resposta = cliente_api.post("/consultas", json={"pergunta": "Algo fora do corpus?"})

    assert resposta.status_code == 200
    assert resposta.json() == {"texto": FRASE_ABSTENCAO, "abstencao": True, "fontes": []}


def test_consulta_aceita_pergunta_com_1000_caracteres(cliente_api, monkeypatch):
    monkeypatch.setattr("app.geracao.respondedor.recuperar", lambda *a, **k: [])

    resposta = cliente_api.post("/consultas", json={"pergunta": "x" * 1000})

    assert resposta.status_code == 200
    assert resposta.json()["abstencao"] is True


@pytest.mark.parametrize(
    "corpo",
    [{"pergunta": ""}, {"pergunta": "   "}, {"pergunta": "x" * 1001}, {}],
    ids=["vazia", "so_espacos", "longa_demais", "sem_campo"],
)
def test_consulta_rejeita_pergunta_invalida(cliente_api, llm_falso, corpo):
    resposta = cliente_api.post("/consultas", json=corpo)

    assert resposta.status_code == 422
    assert llm_falso.chamadas == []
