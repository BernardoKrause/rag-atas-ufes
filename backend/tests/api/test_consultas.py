import json
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
        orgaos_recebidos.append(kwargs.get("orgao"))
        return [_evidencia(item, 1)]

    orgaos_recebidos = []

    monkeypatch.setattr("app.geracao.respondedor.recuperar", recuperar_falso)
    return recebidas, item, orgaos_recebidos


def test_consulta_devolve_resposta_com_fonte_completa(
    cliente_api, llm_falso, perguntas_recebidas
):
    recebidas, item, _ = perguntas_recebidas
    llm_falso.texto = json.dumps({"eventos": [{"evidencia": 1, "relevante": True, "descricao": "O calendário foi aprovado."}]})

    resposta = cliente_api.post("/consultas", json={"pergunta": "  O calendário foi aprovado?  "})

    assert resposta.status_code == 200
    assert recebidas == ["O calendário foi aprovado?"]
    assert resposta.json() == {
        "texto": "01/01/2025: O calendário foi aprovado. [1]",
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
        "configuracao": {
            "provedor": "ollama",
            "modelo": "qwen2.5:7b",
            "max_tokens": 4096,
            "temperatura": 0.0,
            "num_ctx": 16384,
            "orgao": None,
            "escopo": "acervo",
        },
    }


def test_consulta_com_abstencao_do_llm(cliente_api, llm_falso, perguntas_recebidas):
    llm_falso.texto = FRASE_ABSTENCAO

    resposta = cliente_api.post("/consultas", json={"pergunta": "Algo fora do corpus?"})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert (corpo["texto"], corpo["abstencao"], corpo["fontes"]) == (FRASE_ABSTENCAO, True, [])


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


EVENTO = json.dumps({"eventos": [{"evidencia": 1, "relevante": True, "descricao": "O calendário foi aprovado."}]})


def test_consulta_repassa_o_orgao_selecionado(cliente_api, llm_falso, perguntas_recebidas):
    _, _, orgaos = perguntas_recebidas
    llm_falso.texto = EVENTO

    resposta = cliente_api.post("/consultas", json={"pergunta": "O calendário foi aprovado?", "orgao": "CT_DB"})

    assert resposta.status_code == 200
    assert orgaos == ["CT_DB"]
    configuracao = resposta.json()["configuracao"]
    assert (configuracao["orgao"], configuracao["escopo"]) == ("CT_DB", "selecao")


def test_consulta_sem_selecao_usa_o_setor_da_pergunta(cliente_api, llm_falso, perguntas_recebidas):
    _, _, orgaos = perguntas_recebidas
    llm_falso.texto = EVENTO

    resposta = cliente_api.post("/consultas", json={"pergunta": "O calendário foi aprovado no setor CT / DB?"})

    assert orgaos == [None]
    configuracao = resposta.json()["configuracao"]
    assert (configuracao["orgao"], configuracao["escopo"]) == ("CT_DB", "pergunta")


def test_consulta_rejeita_orgao_desconhecido(cliente_api, llm_falso, perguntas_recebidas):
    resposta = cliente_api.post("/consultas", json={"pergunta": "Algo?", "orgao": "XYZ"})

    assert resposta.status_code == 422
    assert llm_falso.chamadas == []


def test_consulta_com_modelo_instalado_usa_cliente_desse_modelo(
    cliente_api, llm_falso, perguntas_recebidas, fabricados
):
    llm_falso.texto = EVENTO

    resposta = cliente_api.post("/consultas", json={"pergunta": "O calendário foi aprovado?", "modelo": "qwen2.5:14b"})
    cliente_api.post("/consultas", json={"pergunta": "De novo?", "modelo": "qwen2.5:14b"})

    assert resposta.status_code == 200
    assert resposta.json()["configuracao"]["modelo"] == "qwen2.5:14b"
    assert fabricados == [None, "qwen2.5:14b"]


def test_consulta_rejeita_modelo_fora_da_lista(cliente_api, llm_falso, perguntas_recebidas):
    resposta = cliente_api.post("/consultas", json={"pergunta": "Algo?", "modelo": "llama3:8b"})

    assert resposta.status_code == 422
    assert llm_falso.chamadas == []


def test_consulta_rejeita_modelo_nao_instalado(cliente_api, llm_falso, perguntas_recebidas, modelos_instalados):
    modelos_instalados.discard("qwen2.5:14b")

    resposta = cliente_api.post("/consultas", json={"pergunta": "Algo?", "modelo": "qwen2.5:14b"})

    assert resposta.status_code == 422
    assert resposta.json()["detail"] == "Modelo não instalado no Ollama."


def test_consulta_registra_a_configuracao_usada(cliente_api, llm_falso, perguntas_recebidas, registro_temporario):
    _, item, _ = perguntas_recebidas
    llm_falso.texto = EVENTO

    cliente_api.post("/consultas", json={"pergunta": "O calendário foi aprovado?", "orgao": "CT_DB"})

    linhas = [json.loads(linha) for linha in registro_temporario.read_text(encoding="utf-8").splitlines()]
    assert len(linhas) == 1
    assert linhas[0]["pergunta"] == "O calendário foi aprovado?"
    assert linhas[0]["configuracao"]["modelo"] == "qwen2.5:7b"
    assert linhas[0]["configuracao"]["orgao"] == "CT_DB"
    assert linhas[0]["fontes"] == [item.item_id_canonico]


def test_orgaos_lista_sigla_nome_e_atas(cliente_api, db_session):
    criar_documento(db_session, nome_arquivo="orgaos_car.pdf", orgao="CAR")

    resposta = cliente_api.get("/orgaos")

    assert resposta.status_code == 200
    car = next(orgao for orgao in resposta.json() if orgao["sigla"] == "CAR")
    assert car == {"sigla": "CAR", "nome": "Centro de Artes", "atas": 1}


def test_modelos_marca_os_instalados(cliente_api, modelos_instalados):
    modelos_instalados.discard("qwen2.5:14b")

    resposta = cliente_api.get("/modelos")

    assert resposta.json() == {
        "padrao": "qwen2.5:7b",
        "modelos": [
            {"nome": "qwen2.5:7b", "disponivel": True},
            {"nome": "qwen2.5:14b", "disponivel": False},
        ],
    }
