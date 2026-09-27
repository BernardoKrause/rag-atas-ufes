import httpx
import pytest

from app.core.config import settings
from app.geracao.llm import ClienteOllama
from app.geracao.respondedor import responder
from app.grafo.construtor import construir_grafo
from app.ingestion.indexador import indexar_e_persistir
from tests.recuperacao.conftest import (  # noqa: F401
    _limpar_itens_pauta_existentes,
    criar_documento,
    criar_item,
    limpar_pontos_qdrant,
)


def _ollama_tem_modelo(modelo):
    try:
        tags = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2).json()
    except httpx.HTTPError:
        return False
    return any(m["name"] == modelo for m in tags.get("models", []))


pytestmark = pytest.mark.skipif(
    not _ollama_tem_modelo(settings.llm_modelo), reason="Ollama indisponível ou modelo ausente"
)


@pytest.fixture()
def cliente_llm():
    return ClienteOllama(
        settings.ollama_base_url, settings.llm_modelo, settings.llm_timeout, settings.llm_max_tokens
    )


@pytest.fixture()
def ata_indexada(db_session, qdrant_cliente, grafo_driver):
    documento = criar_documento(
        db_session, nome_arquivo="e2e_geracao.pdf", orgao="CT_DCC", departamento="DCC",
        numero_reuniao=7, tipo_reuniao="Ordinária",
    )
    itens = [
        criar_item(
            db_session, documento, numero_item="1", item_id_canonico="e2e_ger_1",
            texto="Aprovação da ata da reunião anterior.", assunto="Aprovação de ata",
        ),
        criar_item(
            db_session, documento, numero_item="2", item_id_canonico="e2e_ger_2",
            texto=(
                "O conselho aprovou por unanimidade a criação da disciplina optativa "
                "Aprendizado de Máquina Aplicado, com 60 horas."
            ),
            assunto="Criação de disciplina optativa", tipo_desfecho="Aprovado",
            resultado_votacao="unanimidade",
        ),
        criar_item(
            db_session, documento, numero_item="3", item_id_canonico="e2e_ger_3",
            texto="Informes gerais da chefia sobre o calendário.", assunto="Informes",
        ),
    ]
    indexar_e_persistir(documento.id_documento, itens, qdrant_cliente)
    construir_grafo([(documento, itens)], grafo_driver)
    yield itens
    limpar_pontos_qdrant(qdrant_cliente, documento.id_documento)


def test_pergunta_sobre_conteudo_cita_a_ata_certa(
    db_session, qdrant_cliente, grafo_driver, ata_indexada, cliente_llm
):
    resposta = responder(
        "Qual foi o resultado da votação sobre a disciplina optativa de Aprendizado de Máquina?",
        db_session, qdrant_cliente, grafo_driver, cliente_llm,
    )

    assert resposta.abstencao is False
    assert "e2e_ger_2" in [f.item_id_canonico for f in resposta.fontes]
    assert all(f.rotulo.startswith("Ata CT_DCC, 7ª reunião ordinária") for f in resposta.fontes)


def test_departamento_vem_do_grafo_sem_mencao_textual(
    db_session, qdrant_cliente, grafo_driver, ata_indexada, cliente_llm
):
    assert "DCC" not in ata_indexada[1].texto

    resposta = responder(
        "De qual departamento é a criação da disciplina optativa "
        "Aprendizado de Máquina Aplicado?",
        db_session, qdrant_cliente, grafo_driver, cliente_llm,
    )

    assert resposta.abstencao is False
    assert "DCC" in resposta.texto
    assert "e2e_ger_2" in [f.item_id_canonico for f in resposta.fontes]


def test_pergunta_fora_do_corpus_abstem(
    db_session, qdrant_cliente, grafo_driver, ata_indexada, cliente_llm
):
    resposta = responder(
        "Qual é a capital da França?", db_session, qdrant_cliente, grafo_driver, cliente_llm
    )

    assert resposta.abstencao is True
    assert resposta.fontes == []
