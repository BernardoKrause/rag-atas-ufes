import json
import logging
import re
from datetime import date

import pytest

from app.geracao.prompt import ESQUEMA_EVENTOS, ESQUEMA_RESPOSTA, FRASE_ABSTENCAO, SISTEMA_RESPOSTA
from app.geracao.respondedor import responder, responder_detalhado
from app.geracao.tipos import ErroGeracao, SaidaLLM
from app.recuperacao.tipos import Evidencia
from tests.recuperacao.conftest import criar_documento, criar_item


class LLMFalso:
    def __init__(self, eventos=None, resposta='{"resposta": ""}', truncada=False, erro=None):
        self.eventos = eventos or {}
        self.resposta = resposta
        self.truncada = truncada
        self.erro = erro
        self.chamadas = []
        self.esquemas = []

    def gerar(self, sistema, usuario, esquema=None):
        self.chamadas.append((sistema, usuario))
        self.esquemas.append(esquema)
        if self.erro:
            raise self.erro
        if esquema == ESQUEMA_RESPOSTA:
            return SaidaLLM(texto=self.resposta, truncada=False)
        numero = int(re.search(r'"identificador": (\d+)', usuario).group(1))
        return SaidaLLM(texto=self.eventos.get(numero, _json((numero, False, ""))), truncada=self.truncada)


def _json(*eventos):
    return json.dumps({"eventos": [
        {"evidencia": n, "relevante": relevante, "descricao": descricao}
        for n, relevante, descricao in eventos
    ]}, ensure_ascii=False)


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
    llm = LLMFalso()

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
    llm = LLMFalso()

    resposta = _responder(db_session, llm)

    assert resposta.abstencao is True
    assert resposta.texto == FRASE_ABSTENCAO
    assert resposta.fontes == []
    assert llm.chamadas == []


def test_resposta_lista_so_a_fonte_do_evento_relevante(db_session, dois_itens):
    _, item_b = dois_itens
    llm = LLMFalso(eventos={2: _json((2, True, "O item B foi aprovado."))})

    resposta = _responder(db_session, llm)

    assert resposta.abstencao is False
    assert resposta.texto == "01/01/2025: O item B foi aprovado. [2]"
    assert [f.item_id_canonico for f in resposta.fontes] == [item_b.item_id_canonico]
    assert resposta.fontes[0].numero == 2
    assert resposta.fontes[0].rotulo.startswith("Ata CT_DB, ")


def test_evento_traz_o_desfecho_do_grafo_mesmo_que_o_modelo_o_omita(db_session, monkeypatch):
    documento = criar_documento(db_session, nome_arquivo="resp_4.pdf")
    item = criar_item(db_session, documento, numero_item="1", texto="Aprovado por unanimidade.")
    evidencia = Evidencia(
        item_id_canonico=item.item_id_canonico, texto=item.texto,
        contexto_grafo={"resultado_votacao": "Aprovado por unanimidade", "ato_emitido": "DECISAO_73_2025"},
        rank_final=1, scores={"lexico": None, "vetorial": None, "grafo": None},
    )
    monkeypatch.setattr("app.geracao.respondedor.recuperar", lambda *a, **k: [evidencia])
    llm = LLMFalso(eventos={1: _json((1, True, "Foram apresentadas alterações."))})

    resposta = _responder(db_session, llm)

    assert resposta.texto == (
        "01/01/2025: Foram apresentadas alterações. "
        "Resultado da votação: Aprovado por unanimidade. Ato emitido: DECISAO_73_2025. [1]"
    )


def test_cada_evidencia_e_avaliada_numa_chamada_separada(db_session, dois_itens):
    llm = LLMFalso()

    _responder(db_session, llm)

    assert llm.esquemas == [ESQUEMA_EVENTOS, ESQUEMA_EVENTOS]
    primeira, segunda = (usuario for _, usuario in llm.chamadas)
    assert '"identificador": 1' in primeira and '"identificador": 2' not in primeira
    assert '"identificador": 2' in segunda and '"identificador": 1' not in segunda
    assert primeira.endswith("Pergunta: pergunta?")


def test_fontes_em_ordem_crescente_de_numero(db_session, dois_itens):
    llm = LLMFalso(eventos={1: _json((1, True, "A.")), 2: _json((2, True, "B."))})
    resposta = _responder(db_session, llm)
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
    llm = LLMFalso(eventos={1: _json((1, True, "Aprovado.")), 2: _json((2, True, "Retirado de pauta."))})

    resposta = _responder(db_session, llm)

    assert resposta.texto == "13/05/2025: Retirado de pauta. [2]\n28/05/2025: Aprovado. [1]"


def test_evento_atribuido_a_outra_evidencia_e_descartado(db_session, dois_itens):
    llm = LLMFalso(eventos={1: _json((2, True, "Foi aprovado.")), 2: _json((7, True, "Inventado."))})
    resposta = _responder(db_session, llm)
    assert resposta.abstencao is True
    assert resposta.fontes == []
    assert resposta.texto == FRASE_ABSTENCAO


def test_nenhuma_evidencia_relevante_vira_abstencao(db_session, dois_itens):
    resposta = _responder(db_session, LLMFalso())
    assert resposta.abstencao is True
    assert resposta.fontes == []


def test_saida_que_nao_e_json_e_ignorada_e_loga_aviso(db_session, dois_itens, caplog):
    llm = LLMFalso(eventos={1: "O item A foi aprovado [1].", 2: _json((2, True, "B."))})
    with caplog.at_level(logging.WARNING, logger="app.geracao.respondedor"):
        resposta = _responder(db_session, llm)
    assert resposta.texto == "01/01/2025: B. [2]"
    assert "JSON" in caplog.text


def test_frase_de_abstencao_numa_evidencia_a_torna_irrelevante(db_session, dois_itens):
    llm = LLMFalso(eventos={1: FRASE_ABSTENCAO, 2: _json((2, True, "B."))})
    resposta = _responder(db_session, llm)
    assert resposta.abstencao is False
    assert [f.numero for f in resposta.fontes] == [2]


def test_erro_do_llm_propaga(db_session, dois_itens):
    with pytest.raises(ErroGeracao):
        _responder(db_session, LLMFalso(erro=ErroGeracao("fora do ar")))


def test_saida_truncada_loga_aviso_e_segue(db_session, dois_itens, caplog):
    llm = LLMFalso(eventos={1: _json((1, True, "Parcial."))}, truncada=True)
    with caplog.at_level(logging.WARNING, logger="app.geracao.respondedor"):
        resposta = _responder(db_session, llm)
    assert resposta.abstencao is False
    assert "truncada" in caplog.text


def test_detalhada_guarda_uma_saida_por_evidencia(db_session, dois_itens):
    llm = LLMFalso(eventos={2: _json((2, True, "B."))}, resposta='{"resposta": "B [2]."}')
    detalhada = responder_detalhado("pergunta?", db_session, None, None, llm)
    assert len(detalhada.saidas_eventos) == 2
    assert detalhada.saida_resposta.texto == '{"resposta": "B [2]."}'


def test_pede_eventos_e_depois_a_resposta_direta(db_session, dois_itens):
    llm = LLMFalso(eventos={1: _json((1, True, "ok"))})
    _responder(db_session, llm)
    assert llm.esquemas == [ESQUEMA_EVENTOS, ESQUEMA_EVENTOS, ESQUEMA_RESPOSTA]
    assert llm.chamadas[2][0] == SISTEMA_RESPOSTA


def test_resposta_direta_recebe_so_os_eventos_validados(db_session, dois_itens):
    llm = LLMFalso(eventos={2: _json((2, True, "B."))}, resposta='{"resposta": "B [2]."}')
    _responder(db_session, llm)
    _, usuario = llm.chamadas[2]
    assert '"identificador": 2' in usuario
    assert '"descricao": "B."' in usuario
    assert '"identificador": 1' not in usuario
    assert "texto B" not in usuario


def test_resposta_direta_vem_antes_dos_eventos(db_session, dois_itens):
    llm = LLMFalso(
        eventos={2: _json((2, True, "O item B foi aprovado."))},
        resposta='{"resposta": "Foi aprovado em reunião ordinária [2]."}',
    )

    resposta = _responder(db_session, llm)

    assert resposta.texto == (
        "Foi aprovado em reunião ordinária [2].\n\n01/01/2025: O item B foi aprovado. [2]"
    )


def test_resposta_direta_invalida_fica_de_fora(db_session, dois_itens):
    llm = LLMFalso(
        eventos={1: _json((1, True, "A.")), 2: _json((2, True, "O item B foi aprovado."))},
        resposta='{"resposta": "Foi encaminhado às Direções."}',
    )

    resposta = _responder(db_session, llm)

    assert resposta.texto == "01/01/2025: A. [1]\n01/01/2025: O item B foi aprovado. [2]"


def test_sem_evento_relevante_nao_pede_resposta_direta(db_session, dois_itens):
    llm = LLMFalso()
    _responder(db_session, llm)
    assert ESQUEMA_RESPOSTA not in llm.esquemas


def test_evento_com_termo_da_pergunta_ausente_do_trecho_e_descartado(db_session, dois_itens):
    item_a, _ = dois_itens
    llm = LLMFalso(eventos={
        1: _json((1, True, "O item A foi aprovado.")),
        2: _json((2, True, "Os PADs do DAV foram aprovados.")),
    })

    resposta = responder("Qual foi a decisão sobre os PADs do DAV?", db_session, None, None, llm)

    assert resposta.texto == "01/01/2025: O item A foi aprovado. [1]"
    assert [f.item_id_canonico for f in resposta.fontes] == [item_a.item_id_canonico]
    assert "Os PADs do DAV foram aprovados" not in llm.chamadas[-1][1]


def test_todos_os_eventos_sem_apoio_levam_a_abstencao(db_session, dois_itens):
    llm = LLMFalso(eventos={2: _json((2, True, "Os PADs do DAV foram aprovados."))})

    resposta = responder("Qual foi a decisão sobre os PADs do DAV?", db_session, None, None, llm)

    assert resposta.abstencao is True
    assert resposta.texto == FRASE_ABSTENCAO
