from app.avaliacao import ragas_avaliacao, rodada
from app.avaliacao.jsonl import anexar_jsonl, ler_jsonl


class _Juiz:
    def __init__(self, *args, **kwargs):
        self.saidas = []


def _preparar(monkeypatch, chamadas):
    async def pontuar(metrica, **argumentos):
        chamadas.append((metrica, argumentos.get("response")))
        return 0.5, None

    monkeypatch.setattr(ragas_avaliacao, "JuizOllama", _Juiz)
    monkeypatch.setattr(ragas_avaliacao, "EmbeddingsSerafim", lambda: None)
    monkeypatch.setattr(ragas_avaliacao, "criar_metricas", lambda juiz, emb: {m: m for m in rodada.METRICAS_RAGAS})
    monkeypatch.setattr(ragas_avaliacao, "_pontuar", pontuar)
    monkeypatch.setattr(rodada, "referencias_anonimizadas", lambda refs, saida, sessao: {"P1": "ref"})


def _geracao(condicao, texto):
    return {"pergunta_id": "P1", "condicao": condicao, "repeticao": 1, "texto": texto,
            "abstencao": False, "contextos": ["c1", "c2"]}


REFERENCIA = [{"identificador": "P1", "enunciado": "pergunta?", "evidencias": [{"identificador_item": "i1"}]}]


def test_entrada_identica_reaproveita_sem_chamar_o_juiz(monkeypatch, tmp_path):
    chamadas = []
    _preparar(monkeypatch, chamadas)
    geracao = tmp_path / "geracao_r1.jsonl"
    for condicao, texto in [("hibrida", "r"), ("hibrida_campos", "outra"), ("expandida", "r")]:
        anexar_jsonl(geracao, _geracao(condicao, texto))

    total = rodada.etapa_ragas(REFERENCIA, tmp_path, geracao, list(rodada.CONDICOES), None)

    registros = {r["condicao"]: r for r in ler_jsonl(tmp_path / "ragas.jsonl")}
    assert total == 3
    assert len(chamadas) == 8
    assert registros["expandida"]["reaproveitado_de"] == "hibrida"
    assert registros["expandida"]["faithfulness"] == registros["hibrida"]["faithfulness"]
    assert registros["expandida"]["entrada_sha256"] == registros["hibrida"]["entrada_sha256"]
    assert registros["hibrida_campos"]["entrada_sha256"] != registros["hibrida"]["entrada_sha256"]
    assert "reaproveitado_de" not in registros["hibrida_campos"]


def test_retomada_reaproveita_registro_antigo_sem_chave(monkeypatch, tmp_path):
    chamadas = []
    _preparar(monkeypatch, chamadas)
    geracao = tmp_path / "geracao_r1.jsonl"
    anexar_jsonl(geracao, _geracao("hibrida", "r"))
    anexar_jsonl(geracao, _geracao("expandida", "r"))
    anexar_jsonl(tmp_path / "ragas.jsonl", {
        "pergunta_id": "P1", "condicao": "hibrida", "repeticao": 1, "modelo_juiz": "x",
        **dict.fromkeys(rodada.METRICAS_RAGAS, 0.9), "erros": {}, "segundos": {}, "saidas_juiz": {},
    })

    rodada.etapa_ragas(REFERENCIA, tmp_path, geracao, list(rodada.CONDICOES), None)

    registros = {r["condicao"]: r for r in ler_jsonl(tmp_path / "ragas.jsonl")}
    assert chamadas == []
    assert registros["expandida"]["reaproveitado_de"] == "hibrida"
    assert registros["expandida"]["context_recall"] == 0.9


def test_registro_com_erro_nao_e_reaproveitado(monkeypatch, tmp_path):
    chamadas = []
    _preparar(monkeypatch, chamadas)
    geracao = tmp_path / "geracao_r1.jsonl"
    anexar_jsonl(geracao, _geracao("hibrida", "r"))
    anexar_jsonl(geracao, _geracao("expandida", "r"))
    anexar_jsonl(tmp_path / "ragas.jsonl", {
        "pergunta_id": "P1", "condicao": "hibrida", "repeticao": 1, "modelo_juiz": "x",
        **dict.fromkeys(rodada.METRICAS_RAGAS, None), "erros": {"faithfulness": "tempo esgotado"},
        "segundos": {}, "saidas_juiz": {},
    })

    rodada.etapa_ragas(REFERENCIA, tmp_path, geracao, list(rodada.CONDICOES), None)

    registros = {r["condicao"]: r for r in ler_jsonl(tmp_path / "ragas.jsonl")}
    assert len(chamadas) == 4
    assert "reaproveitado_de" not in registros["expandida"]
