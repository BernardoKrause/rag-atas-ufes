import json

import pytest

from app.api.numeros import ocultar_numeros, revelar_na_resposta
from app.geracao.tipos import Fonte, Resposta
from app.models.documento import NumeroProcesso
from app.recuperacao.tipos import Evidencia
from tests.recuperacao.conftest import criar_documento, criar_item

NUMERO = "99999.000001/2025-11"
TOKEN = "PROCESSO_990001"


@pytest.fixture()
def numero_conhecido(db_session):
    db_session.add(NumeroProcesso(token=TOKEN, numero=NUMERO))
    db_session.flush()


def _fonte(trecho):
    return Fonte(1, "i", 1, "rótulo", trecho, None)


def test_revela_numero_no_texto_e_no_trecho(db_session, numero_conhecido):
    resposta = Resposta(f"Documento avulso nº {TOKEN} [1]", [_fonte(f"Processo {TOKEN} aprovado")], False)

    revelada = revelar_na_resposta(resposta, db_session)

    assert revelada.texto == f"Documento avulso nº {NUMERO} [1]"
    assert revelada.fontes[0].trecho == f"Processo {NUMERO} aprovado"


def test_token_sem_numero_conhecido_continua_como_esta(db_session, numero_conhecido):
    resposta = Resposta("PROCESSO_990002 e PESSOA_123", [], False)
    assert revelar_na_resposta(resposta, db_session).texto == "PROCESSO_990002 e PESSOA_123"


def test_pergunta_com_numero_vira_token_mesmo_com_espacos(db_session, numero_conhecido):
    assert ocultar_numeros(f"O que houve com {NUMERO}?", db_session) == f"O que houve com {TOKEN}?"
    assert ocultar_numeros("Processo 99999. 000001/2025- 11?", db_session) == f"Processo {TOKEN}?"


def test_pergunta_com_numero_desconhecido_nao_muda(db_session, numero_conhecido):
    assert ocultar_numeros("Processo 99999.000002/2025-11?", db_session) == "Processo 99999.000002/2025-11?"


def test_rota_usa_token_na_recuperacao_e_numero_na_saida(
    cliente_api, llm_falso, db_session, numero_conhecido, monkeypatch
):
    documento = criar_documento(db_session, nome_arquivo="num_1.pdf")
    item = criar_item(db_session, documento, numero_item="1", texto=f"Processo {TOKEN}. Aprovado.")
    recebidas = []

    def recuperar_falso(pergunta, *args, **kwargs):
        recebidas.append(pergunta)
        return [Evidencia(item.item_id_canonico, item.texto, {}, 1, {})]

    monkeypatch.setattr("app.geracao.respondedor.recuperar", recuperar_falso)
    llm_falso.texto = json.dumps(
        {"eventos": [{"evidencia": 1, "relevante": True, "descricao": f"O processo {TOKEN} foi aprovado."}]}
    )

    resposta = cliente_api.post("/consultas", json={"pergunta": f"E o {NUMERO}?"}).json()

    assert recebidas == [f"E o {TOKEN}?"]
    assert TOKEN not in resposta["texto"]
    assert NUMERO in resposta["texto"]
    assert resposta["fontes"][0]["trecho"] == f"Processo {NUMERO}. Aprovado."
