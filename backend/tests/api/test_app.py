import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.geracao.tipos import ErroGeracao
from app.main import criar_app


def test_api_nao_sobe_com_config_de_llm_invalida():
    def fabrica_invalida():
        raise ErroGeracao("LLM_MODELO vazio no .env")

    with pytest.raises(ErroGeracao, match="LLM_MODELO vazio"):
        with TestClient(criar_app(fabrica_llm=fabrica_invalida)):
            pass


def test_lifespan_guarda_clientes_no_estado(llm_falso):
    app = criar_app(fabrica_llm=lambda: llm_falso)
    with TestClient(app):
        assert app.state.cliente_llm is llm_falso
        assert app.state.cliente_qdrant is not None
        assert app.state.driver is not None
        assert app.state.fabrica_sessao is not None


def test_health(cliente_api):
    resposta = cliente_api.get("/health")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_cors_permite_origem_configurada(cliente_api):
    origem = settings.cors_origens[0]
    resposta = cliente_api.get("/health", headers={"Origin": origem})
    assert resposta.headers["access-control-allow-origin"] == origem


def test_cors_ignora_origem_desconhecida(cliente_api):
    resposta = cliente_api.get("/health", headers={"Origin": "http://intruso.example"})
    assert "access-control-allow-origin" not in resposta.headers


def test_cors_origens_lidas_do_env_em_json(monkeypatch):
    monkeypatch.setenv("CORS_ORIGENS", '["http://a.example", "http://b.example"]')
    assert Settings().cors_origens == ["http://a.example", "http://b.example"]
