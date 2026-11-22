import pytest
from fastapi.testclient import TestClient

from app.api.dependencias import obter_sessao
from app.geracao.tipos import SaidaLLM
from app.main import criar_app
from tests.recuperacao.conftest import _limpar_itens_pauta_existentes  # noqa: F401


class LLMFalso:
    def __init__(self, texto="", erro=None):
        self.texto = texto
        self.erro = erro
        self.chamadas = []

    def gerar(self, sistema, usuario, esquema=None):
        self.chamadas.append((sistema, usuario))
        if self.erro:
            raise self.erro
        return SaidaLLM(texto=self.texto, truncada=False)


@pytest.fixture()
def llm_falso():
    return LLMFalso()


@pytest.fixture(autouse=True)
def registro_temporario(tmp_path, monkeypatch):
    caminho = tmp_path / "consultas.jsonl"
    monkeypatch.setattr("app.api.rotas.settings.consultas_registro", caminho)
    return caminho


@pytest.fixture()
def modelos_instalados():
    return {"qwen2.5:7b", "qwen2.5:14b"}


@pytest.fixture()
def fabricados():
    return []


@pytest.fixture()
def cliente_api(db_session, llm_falso, modelos_instalados, fabricados):
    def fabrica(modelo=None):
        fabricados.append(modelo)
        return llm_falso

    app = criar_app(fabrica_llm=fabrica, verificar_modelos=lambda: modelos_instalados)
    app.dependency_overrides[obter_sessao] = lambda: db_session
    with TestClient(app, raise_server_exceptions=False) as cliente:
        yield cliente
