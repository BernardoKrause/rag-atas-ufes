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


@pytest.fixture()
def cliente_api(db_session, llm_falso):
    app = criar_app(fabrica_llm=lambda: llm_falso)
    app.dependency_overrides[obter_sessao] = lambda: db_session
    with TestClient(app, raise_server_exceptions=False) as cliente:
        yield cliente
