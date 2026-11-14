import json
import logging
from datetime import date

import pytest

from app.geracao.prompt import ESQUEMA_EVENTOS, ESQUEMA_RESPOSTA, FRASE_ABSTENCAO, SISTEMA_RESPOSTA
from app.geracao.respondedor import responder
from app.geracao.tipos import ErroGeracao, SaidaLLM
from app.recuperacao.tipos import Evidencia
from tests.recuperacao.conftest import criar_documento, criar_item


class LLMFalso:
    def __init__(self, texto="", truncada=False, erro=None, respostas=None):
        self.texto = texto
        self.respostas = list(respostas or [])
        self.truncada = truncada
        self.erro = erro
        self.chamadas = []
        self.esquemas = []

    def gerar(self, sistema, usuario, esquema=None):
        self.chamadas.append((sistema, usuario))
        self.esquemas.append(esquema)
        if self.erro:
            raise self.erro
        if len(self.chamadas) > 1 and self.respostas:
            return SaidaLLM(texto=self.respostas.pop(0), truncada=False)
        return SaidaLLM(texto=self.texto, truncada=self.truncada)


def _evidencia(item, rank):
    return Evidencia(
        item_id_canonico=item.item_id_canonico, texto=item.texto, contexto_grafo={},
        rank_final=rank, scores={"lexico": None, "vetorial": None, "grafo": None},
    )


@pytest.fixture()
def dois_itens(db_session, monkeypatch):
    documento = criar_documento(db_session, nome_arquivo="resp_1.pdf", orgao="CT_DB")
    item_a = criar_item(db_session, documento, numero_item="1", texto="texto A")
    item_b = criar_item(db_session, documento, numero_item="2", texto="texto B")
    monkeypatch.setattr(
        "app.geracao.respondedor.recuperar",
        lambda *args, **kwargs: [_evidencia(item_a, 1), _evidencia(item_b, 2)],
    )
    return item_a, item_b


def _responder(db_session, llm):
    return responder("pergunta?", db_session, None, None, llm)


def test_recuperacao_vazia_abstem_sem_chamar_llm(db_session, monkeypatch):
    monkeypatch.setattr("app.geracao.respondedor.recuperar", lambda *a, **k: [])
    llm = LLMFalso(texto="não deveria ser chamado [1]")

    resposta = _responder(db_session, llm)

    assert resposta.abstencao is True
    assert resposta.texto == FRASE_ABSTENCAO
    assert resposta.fontes == []
    assert llm.chamadas == []


def test_evidencias_ausentes_do_postgres_abstem_sem_chamar_llm(db_session, monkeypatch):
    fantasma = Evidencia(
        item_id_canonico="item_que_nao_existe", texto="texto órfão", contexto_grafo={},
        rank_final=1, scores={"lexico": None, "vetorial": None, "grafo": None},
    )
    monkeypatch.setattr("app.geracao.respondedor.recuperar", lambda *a, **k: [fantasma])
    llm = LLMFalso(texto="não deveria ser chamado [1]")

    resposta = _responder(db_session, llm)

    assert resposta.abstencao is True
    assert resposta.texto == FRASE_ABSTENCAO
    assert resposta.fontes == []
    assert llm.chamadas == []


def _json(*eventos):
    return json.dumps({"eventos": [
        {"evidencia": n, "relevante": relevante, "descricao": descricao}
        for n, relevante, descricao in eventos
    ]}, ensure_ascii=False)


def test_resposta_lista_so_a_fonte_do_evento_relevante(db_session, dois_itens):
    _, item_b = dois_itens
    saida = _json((1, False, ""), (2, True, "O item B foi aprovado."))

    resposta = _responder(db_session, LLMFalso(texto=saida))

    assert resposta.abstencao is False
    assert resposta.texto == "01/01/2025: O item B foi aprovado. [2]"
    assert [f.item_id_canonico for f in resposta.fontes] == [item_b.item_id_canonico]
    assert resposta.fontes[0].numero == 2
    assert resposta.fontes[0].rotulo.startswith("Ata CT_DB, ")


def test_fontes_em_ordem_crescente_de_numero(db_session, dois_itens):
    resposta = _responder(db_session, LLMFalso(texto=_json((2, True, "B."), (1, True, "A."))))
    assert [f.numero for f in resposta.fontes] == [1, 2]


def test_eventos_saem_em_ordem_de_data_da_reuniao(db_session, monkeypatch):
    recente = criar_documento(db_session, nome_arquivo="resp_2.pdf", data_reuniao=date(2025, 5, 28))
    antiga = criar_documento(db_session, nome_arquivo="resp_3.pdf", data_reuniao=date(2025, 5, 13))
    item_recente = criar_item(db_session, recente, numero_item="1", texto="aprovado")
    item_antigo = criar_item(db_session, antiga, numero_item="1", texto="retirado de pauta")
    monkeypatch.setattr(
        "app.geracao.respondedor.recuperar",
        lambda *a, **k: [_evidencia(item_recente, 1), _evidencia(item_antigo, 2)],
    )
    saida = _json((1, True, "Aprovado."), (2, True, "Retirado de pauta."))

    resposta = _responder(db_session, LLMFalso(texto=saida))

    assert resposta.texto == "13/05/2025: Retirado de pauta. [2]\n28/05/2025: Aprovado. [1]"


def test_identificador_fora_do_contexto_vira_abstencao(db_session, dois_itens):
    resposta = _responder(db_session, LLMFalso(texto=_json((7, True, "Foi aprovado."))))
    assert resposta.abstencao is True
    assert resposta.fontes == []
    assert resposta.texto == FRASE_ABSTENCAO


def test_nenhuma_evidencia_relevante_vira_abstencao(db_session, dois_itens):
    resposta = _responder(db_session, LLMFalso(texto=_json((1, False, ""), (2, False, ""))))
    assert resposta.abstencao is True
    assert resposta.fontes == []


def test_saida_que_nao_e_json_vira_abstencao_e_loga_aviso(db_session, dois_itens, caplog):
    with caplog.at_level(logging.WARNING, logger="app.geracao.respondedor"):
        resposta = _responder(db_session, LLMFalso(texto="O item B foi aprovado [2]."))
    assert resposta.abstencao is True
    assert "JSON" in caplog.text


def test_resposta_com_frase_de_abstencao_vira_abstencao(db_session, dois_itens):
    resposta = _responder(db_session, LLMFalso(texto=FRASE_ABSTENCAO))
    assert resposta.abstencao is True
    assert resposta.fontes == []


def test_erro_do_llm_propaga(db_session, dois_itens):
    with pytest.raises(ErroGeracao):
        _responder(db_session, LLMFalso(erro=ErroGeracao("fora do ar")))


def test_saida_truncada_loga_aviso_e_segue(db_session, dois_itens, caplog):
    with caplog.at_level(logging.WARNING, logger="app.geracao.respondedor"):
        resposta = _responder(db_session, LLMFalso(texto=_json((1, True, "Parcial.")), truncada=True))
    assert resposta.abstencao is False
    assert "truncada" in caplog.text


def test_prompt_enviado_traz_um_registro_por_evidencia(db_session, dois_itens):
    llm = LLMFalso(texto=_json((1, True, "ok")))
    _responder(db_session, llm)
    _, usuario = llm.chamadas[0]
    assert '"identificador": 1' in usuario
    assert '"identificador": 2' in usuario
    assert usuario.endswith("Pergunta: pergunta?")


def test_pede_eventos_e_depois_a_resposta_direta(db_session, dois_itens):
    llm = LLMFalso(texto=_json((1, True, "ok")))
    _responder(db_session, llm)
    assert llm.esquemas == [ESQUEMA_EVENTOS, ESQUEMA_RESPOSTA]
    assert llm.chamadas[1][0] == SISTEMA_RESPOSTA


def test_resposta_direta_recebe_so_as_evidencias_dos_eventos(db_session, dois_itens):
    llm = LLMFalso(texto=_json((1, False, ""), (2, True, "B.")), respostas=['{"resposta": "B."}'])
    _responder(db_session, llm)
    _, usuario = llm.chamadas[1]
    assert '"identificador": 2' in usuario
    assert '"identificador": 1' not in usuario


def test_resposta_direta_vem_antes_dos_eventos(db_session, dois_itens):
    llm = LLMFalso(
        texto=_json((2, True, "O item B foi aprovado.")),
        respostas=['{"resposta": "Foi aprovado."}'],
    )

    resposta = _responder(db_session, llm)

    assert resposta.texto == "Foi aprovado.\n\n01/01/2025: O item B foi aprovado. [2]"


def test_sem_evento_relevante_nao_pede_resposta_direta(db_session, dois_itens):
    llm = LLMFalso(texto=_json((1, False, "")))
    _responder(db_session, llm)
    assert len(llm.chamadas) == 1
