import anthropic
import httpx
import pytest
from pydantic import SecretStr

from app.avaliacao import executar
from app.geracao.tipos import ErroGeracao


def test_etapa_desconhecida_sai_com_erro():
    with pytest.raises(SystemExit):
        executar.main(["inventada"])


def test_etapa_de_rodada_exige_rodada(capsys):
    assert executar.main(["recuperacao"]) == 1
    assert "--rodada" in capsys.readouterr().err


def test_geracao_recusa_modelo_diferente(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(executar.settings, "llm_provedor", "ollama")
    monkeypatch.setattr(executar.settings, "llm_modelo", "qwen2.5:7b")
    gt = tmp_path / "gt.yaml"
    gt.write_text("perguntas: []\n", encoding="utf-8")

    assert executar.main(["geracao", "--rodada", "t", "--ground-truth", str(gt)]) == 1
    assert "claude-sonnet-5-5" in capsys.readouterr().err


def test_filtra_perguntas_por_id(tmp_path):
    gt = tmp_path / "gt.yaml"
    gt.write_text(
        "perguntas:\n  - {id: q1, categoria: intra_exata}\n  - {id: q2, categoria: intra_exata}\n",
        encoding="utf-8",
    )

    perguntas = executar.carregar_perguntas(gt, "q2")

    assert [p.id for p in perguntas] == ["q2"]


def test_falha_da_api_devolve_1_com_mensagem_de_retomada(monkeypatch, capsys, tmp_path):
    gt = tmp_path / "gt.yaml"
    gt.write_text("perguntas: []\n", encoding="utf-8")
    erro = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))

    def levantar(args, perguntas):
        raise erro

    monkeypatch.setattr(executar, "_rodar", levantar)

    assert executar.main(["recuperacao", "--rodada", "t", "--ground-truth", str(gt)]) == 1
    assert "retomar" in capsys.readouterr().err


def test_erro_de_geracao_tem_mensagem_propria(monkeypatch, capsys, tmp_path):
    gt = tmp_path / "gt.yaml"
    gt.write_text("perguntas: []\n", encoding="utf-8")

    def levantar(args, perguntas):
        raise ErroGeracao("quebrou")

    monkeypatch.setattr(executar, "_rodar", levantar)

    assert executar.main(["recuperacao", "--rodada", "t", "--ground-truth", str(gt)]) == 1
    erro = capsys.readouterr().err
    assert "erro na geração: quebrou" in erro
    assert "API da Anthropic" not in erro


@pytest.mark.parametrize("chave", [None, SecretStr("   ")])
def test_ragas_sem_chave_devolve_1(monkeypatch, capsys, tmp_path, chave):
    gt = tmp_path / "gt.yaml"
    gt.write_text("perguntas: []\n", encoding="utf-8")
    monkeypatch.setattr(executar.settings, "anthropic_api_key", chave)

    assert executar.main(["ragas", "--rodada", "t", "--ground-truth", str(gt)]) == 1
    assert "a etapa ragas exige ANTHROPIC_API_KEY no .env" in capsys.readouterr().err


def test_problemas_dos_indices_tudo_certo():
    assert executar.problemas_dos_indices(357, 357, 8942) == []


def test_problemas_dos_indices_grafo_vazio():
    problemas = executar.problemas_dos_indices(357, 0, 8942)

    assert len(problemas) == 1
    assert "357" in problemas[0] and "0" in problemas[0]


def test_problemas_dos_indices_qdrant_vazio():
    assert len(executar.problemas_dos_indices(357, 357, 0)) == 1


def test_problemas_dos_indices_sem_documentos():
    problemas = executar.problemas_dos_indices(0, 0, 0)

    assert any("documento" in problema for problema in problemas)
