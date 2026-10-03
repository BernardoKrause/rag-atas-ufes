import pytest

from app.core.config import settings
from app.geracao.tipos import ErroGeracao
from app.recuperacao.tipos import Evidencia
from tests.recuperacao.conftest import criar_documento, criar_item


@pytest.fixture(autouse=True)
def uma_evidencia(db_session, monkeypatch):
    documento = criar_documento(db_session, nome_arquivo="api_erro.pdf")
    item = criar_item(db_session, documento, numero_item="1", texto="texto")
    evidencia = Evidencia(
        item_id_canonico=item.item_id_canonico, texto=item.texto, contexto_grafo={},
        rank_final=1, scores={"lexico": None, "vetorial": None, "grafo": None},
    )
    monkeypatch.setattr("app.geracao.respondedor.recuperar", lambda *a, **k: [evidencia])


def test_falha_do_llm_vira_503_sem_vazar_detalhe(cliente_api, llm_falso, caplog):
    llm_falso.erro = ErroGeracao("falha ao chamar o Ollama: http://interno:11434 recusou")

    resposta = cliente_api.post("/consultas", json={"pergunta": "pergunta?"})

    assert resposta.status_code == 503
    assert resposta.json() == {"detail": "Serviço de geração indisponível. Tente novamente."}
    assert "interno" not in resposta.text
    assert "interno:11434" in caplog.text


def test_erro_inesperado_vira_500_sem_vazar_detalhe(cliente_api, llm_falso, caplog):
    llm_falso.erro = RuntimeError("segredo interno")

    resposta = cliente_api.post("/consultas", json={"pergunta": "pergunta?"})

    assert resposta.status_code == 500
    assert resposta.json() == {"detail": "Erro interno."}
    assert "segredo" not in resposta.text
    assert "segredo interno" in caplog.text


def test_erro_500_sai_com_header_cors(cliente_api, llm_falso):
    llm_falso.erro = RuntimeError("x")
    origem = settings.cors_origens[0]

    resposta = cliente_api.post(
        "/consultas", json={"pergunta": "pergunta?"}, headers={"Origin": origem}
    )

    assert resposta.status_code == 500
    assert resposta.headers["access-control-allow-origin"] == origem
