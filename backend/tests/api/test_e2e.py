import pytest
from fastapi.testclient import TestClient

from app.api.dependencias import obter_sessao
from app.core.config import settings
from app.main import criar_app
from tests.geracao.test_e2e import _ollama_tem_modelo, ata_indexada  # noqa: F401
from tests.recuperacao.conftest import grafo_driver  # noqa: F401

pytestmark = pytest.mark.skipif(
    not _ollama_tem_modelo(settings.llm_modelo), reason="Ollama indisponível ou modelo ausente"
)


@pytest.fixture()
def cliente_api_real(db_session):
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: db_session
    with TestClient(app) as cliente:
        yield cliente


def test_departamento_via_grafo_pela_api(cliente_api_real, ata_indexada):  # noqa: F811
    resposta = cliente_api_real.post(
        "/consultas",
        json={
            "pergunta": "De qual departamento é a criação da disciplina optativa "
            "Aprendizado de Máquina Aplicado?"
        },
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["abstencao"] is False
    assert "DCC" in corpo["texto"]
    fonte = next(f for f in corpo["fontes"] if f["item_id_canonico"] == "e2e_ger_2")
    assert "Aprendizado de Máquina Aplicado" in fonte["trecho"]
    assert fonte["url_origem"] == "http://exemplo"
