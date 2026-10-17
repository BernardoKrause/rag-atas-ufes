import pytest

from app.geracao.prompt import FRASE_ABSTENCAO
from app.geracao.respondedor import responder, responder_detalhado
from app.geracao.tipos import SaidaLLM
from app.recuperacao.tipos import Evidencia
from tests.recuperacao.conftest import criar_documento, criar_item


class LLMFalso:
    def __init__(self, texto):
        self.texto = texto

    def gerar(self, sistema, usuario):
        return SaidaLLM(texto=self.texto, truncada=False, tokens_entrada=50, tokens_saida=5)


@pytest.fixture()
def recuperacao_falsa(db_session, monkeypatch):
    documento = criar_documento(db_session, nome_arquivo="det_1.pdf", orgao="CT_DB")
    item = criar_item(db_session, documento, numero_item="1", texto="texto A")
    camadas_recebidas = []

    def recuperar_falso(*args, **kwargs):
        camadas_recebidas.append(kwargs.get("camadas"))
        return [Evidencia(item.item_id_canonico, item.texto, {}, 1, {})]

    monkeypatch.setattr("app.geracao.respondedor.recuperar", recuperar_falso)
    return item, camadas_recebidas


def test_detalhada_traz_evidencias_saida_e_resposta(db_session, recuperacao_falsa):
    item, _ = recuperacao_falsa

    detalhada = responder_detalhado("p?", db_session, None, None, LLMFalso("resposta [1]"))

    assert detalhada.resposta.abstencao is False
    assert [e.fonte.item_id_canonico for e in detalhada.evidencias] == [item.item_id_canonico]
    assert detalhada.saida_llm.tokens_entrada == 50


def test_detalhada_repassa_camadas(db_session, recuperacao_falsa):
    _, camadas_recebidas = recuperacao_falsa

    responder_detalhado(
        "p?", db_session, None, None, LLMFalso("r [1]"), camadas=frozenset({"lexico"})
    )

    assert camadas_recebidas == [frozenset({"lexico"})]


def test_detalhada_abstencao_do_llm_mantem_evidencias_e_saida(db_session, recuperacao_falsa):
    detalhada = responder_detalhado("p?", db_session, None, None, LLMFalso(FRASE_ABSTENCAO))

    assert detalhada.resposta.abstencao is True
    assert len(detalhada.evidencias) == 1
    assert detalhada.saida_llm is not None


def test_detalhada_sem_recuperacao_nao_tem_saida(db_session, monkeypatch):
    monkeypatch.setattr("app.geracao.respondedor.recuperar", lambda *a, **k: [])

    detalhada = responder_detalhado("p?", db_session, None, None, LLMFalso("x"))

    assert detalhada.resposta.abstencao is True
    assert detalhada.evidencias == []
    assert detalhada.saida_llm is None


def test_responder_continua_devolvendo_so_a_resposta(db_session, recuperacao_falsa):
    resposta = responder("p?", db_session, None, None, LLMFalso("resposta [1]"))

    assert resposta.abstencao is False
    assert resposta.fontes[0].numero == 1
