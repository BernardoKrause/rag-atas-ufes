import anthropic
import httpx
import pytest

from app.avaliacao.etapas import (
    CONFIGURACOES,
    etapa_geracao,
    etapa_recuperacao,
    montar_pool,
)
from app.avaliacao.ground_truth import PerguntaReferencia
from app.avaliacao.jsonl import anexar_jsonl, ler_jsonl
from app.geracao.tipos import (
    ErroGeracao,
    EvidenciaNumerada,
    Fonte,
    Resposta,
    RespostaDetalhada,
    SaidaLLM,
)


def _pergunta(id_, categoria="intra_exata"):
    return PerguntaReferencia(
        id=id_, categoria=categoria, origem="autor", pergunta=f"pergunta {id_}?",
        resposta_referencia="r", itens_relevantes=(), trechos_evidencia=(),
        sequencia_cronologica=(), tipo_dificuldade="", observacao="",
    )


MAPA = {"i1": "i1", "i1_F1": "i1", "i2": "i2", "i3": "i3"}


def _recuperar_ids(pergunta, camadas, k):
    if camadas == frozenset({"lexico"}):
        return ["i1_F1", "i1", "i2"][:k]
    return ["i3", "i2"][:k]


def test_jsonl_ida_e_volta(tmp_path):
    caminho = tmp_path / "sub" / "x.jsonl"
    assert ler_jsonl(caminho) == []

    anexar_jsonl(caminho, {"a": 1, "texto": "ação"})
    anexar_jsonl(caminho, {"a": 2})

    assert ler_jsonl(caminho) == [{"a": 1, "texto": "ação"}, {"a": 2}]


def test_recuperacao_grava_as_quatro_configs_com_ranking_logico(tmp_path):
    saida = tmp_path / "recuperacao.jsonl"

    total = etapa_recuperacao(
        [_pergunta("q1"), _pergunta("q2", "sem_evidencia")], _recuperar_ids, MAPA, saida
    )

    registros = ler_jsonl(saida)
    assert total == 8
    assert {r["config"] for r in registros} == set(CONFIGURACOES)
    so_lexico = next(r for r in registros if r["pergunta_id"] == "q1" and r["config"] == "C")
    assert so_lexico["ranking"] == ["i1_F1", "i1", "i2"]
    assert so_lexico["ranking_logico"] == ["i1", "i2"]


def test_recuperacao_sobrescreve_rodada_anterior(tmp_path):
    saida = tmp_path / "recuperacao.jsonl"
    etapa_recuperacao([_pergunta("q1")], _recuperar_ids, MAPA, saida)
    etapa_recuperacao([_pergunta("q1")], _recuperar_ids, MAPA, saida)

    assert len(ler_jsonl(saida)) == 4


def _detalhada(abstencao=False, truncada=False):
    fonte = Fonte(1, "i1_F1", 10, "rótulo", "trecho", 1)
    evidencia = EvidenciaNumerada(1, fonte, "texto do item", ["Frase do grafo."], None, None)
    resposta = Resposta("resp [1]", [] if abstencao else [fonte], abstencao)
    return RespostaDetalhada(resposta, [evidencia], [SaidaLLM("resp [1]", truncada, 100, 20)])


def test_geracao_grava_a_e_b_com_contextos_e_tokens(tmp_path):
    saida = tmp_path / "geracao.jsonl"
    chamadas = []

    def responder_fn(pergunta, camadas):
        chamadas.append(camadas)
        return _detalhada()

    total = etapa_geracao([_pergunta("q1")], responder_fn, MAPA, saida, "claude-sonnet-5-5")

    registros = ler_jsonl(saida)
    assert total == 2
    assert chamadas == [CONFIGURACOES["A"], CONFIGURACOES["B"]]
    registro = registros[0]
    assert registro["fontes"] == ["i1_F1"]
    assert registro["fontes_logicas"] == ["i1"]
    assert registro["contextos"] == ["rótulo\ntexto do item\nFrase do grafo."]
    assert (registro["tokens_entrada"], registro["tokens_saida"]) == (100, 20)
    assert registro["modelo"] == "claude-sonnet-5-5"
    assert registro["erro"] is None


def test_geracao_truncada_grava_erro_truncada_e_mantem_o_resto(tmp_path):
    saida = tmp_path / "geracao.jsonl"

    etapa_geracao(
        [_pergunta("q1")], lambda p, c: _detalhada(abstencao=True, truncada=True), MAPA, saida, "m"
    )

    registro = ler_jsonl(saida)[0]
    assert registro["erro"] == "truncada"
    assert registro["truncada"] is True
    assert registro["contextos"] == ["rótulo\ntexto do item\nFrase do grafo."]
    assert (registro["tokens_entrada"], registro["tokens_saida"]) == (100, 20)
    assert registro["texto"] == "resp [1]"


def test_geracao_soma_tokens_das_duas_chamadas_e_marca_truncada_da_segunda(tmp_path):
    saida = tmp_path / "geracao.jsonl"
    detalhada = _detalhada()
    detalhada = RespostaDetalhada(
        detalhada.resposta, detalhada.evidencias, detalhada.saidas_eventos,
        SaidaLLM('{"resposta": "r"}', True, 30, 4),
    )

    etapa_geracao([_pergunta("q1")], lambda p, c: detalhada, MAPA, saida, "m")

    registro = ler_jsonl(saida)[0]
    assert (registro["tokens_entrada"], registro["tokens_saida"]) == (130, 24)
    assert registro["truncada"] is True
    assert registro["erro"] == "truncada"


def test_geracao_retoma_sem_repetir(tmp_path):
    saida = tmp_path / "geracao.jsonl"
    anexar_jsonl(saida, {"pergunta_id": "q1", "config": "A"})
    chamadas = []

    def responder_fn(pergunta, camadas):
        chamadas.append(camadas)
        return _detalhada()

    total = etapa_geracao([_pergunta("q1")], responder_fn, MAPA, saida, "m")

    assert total == 1
    assert chamadas == [CONFIGURACOES["B"]]


def test_geracao_registra_erro_e_segue(tmp_path):
    saida = tmp_path / "geracao.jsonl"

    def responder_fn(pergunta, camadas):
        raise ErroGeracao("recusou")

    total = etapa_geracao([_pergunta("q1")], responder_fn, MAPA, saida, "m")

    registros = ler_jsonl(saida)
    assert total == 2
    assert all(r["erro"] == "recusou" and r["texto"] is None for r in registros)


def test_geracao_interrompe_em_falha_da_api_sem_gravar_o_par(tmp_path):
    saida = tmp_path / "geracao.jsonl"
    chamadas = []

    def responder_fn(pergunta, camadas):
        chamadas.append(camadas)
        if len(chamadas) == 2:
            conexao = anthropic.APIConnectionError(
                request=httpx.Request("POST", "https://api.anthropic.com")
            )
            raise ErroGeracao("falha") from conexao
        return _detalhada()

    with pytest.raises(ErroGeracao):
        etapa_geracao([_pergunta("q1")], responder_fn, MAPA, saida, "m")

    assert [(r["pergunta_id"], r["config"]) for r in ler_jsonl(saida)] == [("q1", "A")]


def test_geracao_interrompe_em_falha_de_conexao_do_ollama_sem_gravar_o_par(tmp_path):
    saida = tmp_path / "geracao.jsonl"
    chamadas = []

    def responder_fn(pergunta, camadas):
        chamadas.append(camadas)
        if len(chamadas) == 2:
            raise ErroGeracao("falha") from httpx.ConnectError("recusada")
        return _detalhada()

    with pytest.raises(ErroGeracao):
        etapa_geracao([_pergunta("q1")], responder_fn, MAPA, saida, "m")

    assert [(r["pergunta_id"], r["config"]) for r in ler_jsonl(saida)] == [("q1", "A")]


def test_pool_une_configs_e_guarda_melhor_rank():
    linhas = montar_pool([_pergunta("q1")], _recuperar_ids, MAPA, k=10)

    por_item = {linha["item_id"]: linha for linha in linhas}
    assert set(por_item) == {"i1", "i2", "i3"}
    assert por_item["i2"]["configs"] == "A,B,C,D"
    assert por_item["i2"]["melhor_rank"] == 2
    assert por_item["i1"]["configs"] == "C"
    assert [linha["item_id"] for linha in linhas] == ["i1", "i3", "i2"]
