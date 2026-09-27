import logging

import pytest

from app.geracao.prompt import FRASE_ABSTENCAO
from app.geracao.respondedor import responder
from app.geracao.tipos import ErroGeracao, SaidaLLM
from app.recuperacao.tipos import Evidencia
from tests.recuperacao.conftest import criar_documento, criar_item


class LLMFalso:
    def __init__(self, texto="", truncada=False, erro=None):
        self.texto = texto
        self.truncada = truncada
        self.erro = erro
        self.chamadas = []

    def gerar(self, sistema, usuario):
        self.chamadas.append((sistema, usuario))
        if self.erro:
            raise self.erro
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


def test_resposta_com_citacao_valida_lista_so_a_fonte_citada(db_session, dois_itens):
    _, item_b = dois_itens
    resposta = _responder(db_session, LLMFalso(texto="O item B foi aprovado [2]."))

    assert resposta.abstencao is False
    assert resposta.texto == "O item B foi aprovado [2]."
    assert [f.item_id_canonico for f in resposta.fontes] == [item_b.item_id_canonico]
    assert resposta.fontes[0].numero == 2
    assert resposta.fontes[0].rotulo.startswith("Ata CT_DB, ")


def test_fontes_em_ordem_crescente_de_numero(db_session, dois_itens):
    resposta = _responder(db_session, LLMFalso(texto="B [2] e A [1]."))
    assert [f.numero for f in resposta.fontes] == [1, 2]


def test_resposta_sem_marcador_valido_vira_abstencao(db_session, dois_itens):
    resposta = _responder(db_session, LLMFalso(texto="Foi aprovado [7]."))
    assert resposta.abstencao is True
    assert resposta.fontes == []
    assert resposta.texto == FRASE_ABSTENCAO


def test_resposta_com_frase_de_abstencao_vira_abstencao(db_session, dois_itens):
    texto = FRASE_ABSTENCAO.rstrip(".") + " [1]"
    resposta = _responder(db_session, LLMFalso(texto=texto))
    assert resposta.abstencao is True
    assert resposta.fontes == []


def test_erro_do_llm_propaga(db_session, dois_itens):
    with pytest.raises(ErroGeracao):
        _responder(db_session, LLMFalso(erro=ErroGeracao("fora do ar")))


def test_saida_truncada_loga_aviso_e_segue(db_session, dois_itens, caplog):
    with caplog.at_level(logging.WARNING, logger="app.geracao.respondedor"):
        resposta = _responder(db_session, LLMFalso(texto="Parcial [1]", truncada=True))
    assert resposta.abstencao is False
    assert "truncada" in caplog.text


def test_prompt_enviado_contem_evidencias_numeradas(db_session, dois_itens):
    llm = LLMFalso(texto="ok [1]")
    _responder(db_session, llm)
    _, usuario = llm.chamadas[0]
    assert "[1] Ata CT_DB" in usuario
    assert "[2] Ata CT_DB" in usuario
    assert usuario.endswith("Pergunta: pergunta?")
