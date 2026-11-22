import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.geracao.tipos import ErroGeracao
from app.main import criar_app


def test_api_nao_sobe_com_config_de_llm_invalida():
    def fabrica_invalida(modelo=None):
        raise ErroGeracao("LLM_MODELO vazio no .env")

    with pytest.raises(ErroGeracao, match="LLM_MODELO vazio"):
        with TestClient(criar_app(fabrica_llm=fabrica_invalida)):
            pass


def test_lifespan_guarda_clientes_no_estado(llm_falso):
    app = criar_app(fabrica_llm=lambda modelo=None: llm_falso)
    with TestClient(app):
        assert app.state.cliente_llm is llm_falso
        assert app.state.cliente_qdrant is not None
        assert app.state.driver is not None
        assert app.state.fabrica_sessao is not None


def test_lifespan_aquece_modelo_de_embedding(llm_falso, monkeypatch):
    chamadas = []
    monkeypatch.setattr("app.api.dependencias.carregar_modelo", lambda: chamadas.append(1))
    with TestClient(criar_app(fabrica_llm=lambda modelo=None: llm_falso)):
        assert chamadas == [1]


def test_lifespan_fecha_qdrant_se_startup_falha_depois(llm_falso, monkeypatch):
    class QdrantFalso:
        fechado = False

        def close(self):
            self.fechado = True

    qdrant = QdrantFalso()
    monkeypatch.setattr("app.api.dependencias._obter_cliente_qdrant", lambda: qdrant)

    def driver_quebrado():
        raise RuntimeError("neo4j indisponivel")

    monkeypatch.setattr("app.api.dependencias.obter_driver", driver_quebrado)

    with pytest.raises(RuntimeError, match="neo4j indisponivel"):
        with TestClient(criar_app(fabrica_llm=lambda modelo=None: llm_falso)):
            pass
    assert qdrant.fechado


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
