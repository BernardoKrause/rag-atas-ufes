from app.avaliacao.ground_truth import (
    PerguntaReferencia,
    carregar_ground_truth,
    validar_ground_truth,
)

IDS = {"10_PAUTA_1", "11_PAUTA_2", "12_PAUTA_3"}


def _pergunta(**campos):
    base = dict(
        id="q1", categoria="intra_exata", origem="autor", pergunta="O que foi decidido?",
        resposta_referencia="Foi aprovado.", itens_relevantes=("10_PAUTA_1",),
        trechos_evidencia=("aprovado por unanimidade",), sequencia_cronologica=(),
        tipo_dificuldade="", observacao="",
    )
    base.update(campos)
    return PerguntaReferencia(**base)


def test_carrega_yaml_com_campos_ausentes(tmp_path):
    caminho = tmp_path / "gt.yaml"
    caminho.write_text(
        "perguntas:\n"
        "  - id: q1\n"
        "    categoria: intra_exata\n"
        "    origem: servidor\n"
        "    pergunta: Quando foi aprovado o PPC?\n",
        encoding="utf-8",
    )

    [pergunta] = carregar_ground_truth(caminho)

    assert pergunta.id == "q1"
    assert pergunta.origem == "servidor"
    assert pergunta.resposta_referencia == ""
    assert pergunta.itens_relevantes == ()


def test_pergunta_valida_nao_tem_erros():
    assert validar_ground_truth([_pergunta()], IDS) == []


def test_id_repetido():
    erros = validar_ground_truth([_pergunta(), _pergunta()], IDS)

    assert any("repetido" in erro for erro in erros)


def test_categoria_e_origem_invalidas():
    erros = validar_ground_truth([_pergunta(categoria="outra", origem="x")], IDS)

    assert any("categoria" in erro for erro in erros)
    assert any("origem" in erro for erro in erros)


def test_textos_vazios():
    erros = validar_ground_truth([_pergunta(pergunta="", resposta_referencia=" ")], IDS)

    assert len(erros) == 2


def test_item_inexistente():
    erros = validar_ground_truth([_pergunta(itens_relevantes=("99_X_1",))], IDS)

    assert any("99_X_1" in erro for erro in erros)


def test_trechos_e_itens_com_tamanhos_diferentes():
    erros = validar_ground_truth([_pergunta(trechos_evidencia=())], IDS)

    assert any("trechos" in erro for erro in erros)


def test_intra_exige_um_item():
    erros = validar_ground_truth(
        [_pergunta(itens_relevantes=("10_PAUTA_1", "11_PAUTA_2"), trechos_evidencia=("a", "b"))],
        IDS,
    )

    assert any("1 item" in erro for erro in erros)


def test_inter_atas_exige_duas_atas():
    mesma_ata = _pergunta(
        categoria="inter_atas", itens_relevantes=("10_PAUTA_1", "10_PAUTA_9"),
        trechos_evidencia=("a", "b"),
    )

    erros = validar_ground_truth([mesma_ata], IDS | {"10_PAUTA_9"})

    assert any("2 atas" in erro for erro in erros)


def test_sem_evidencia_nao_pode_ter_itens():
    erros = validar_ground_truth([_pergunta(categoria="sem_evidencia")], IDS)

    assert any("sem_evidencia" in erro for erro in erros)


def test_sem_evidencia_valida():
    pergunta = _pergunta(categoria="sem_evidencia", itens_relevantes=(), trechos_evidencia=())

    assert validar_ground_truth([pergunta], IDS) == []


def test_longitudinal_exige_sequencia_dentro_dos_relevantes():
    pergunta = _pergunta(
        categoria="longitudinal", itens_relevantes=("10_PAUTA_1", "11_PAUTA_2"),
        trechos_evidencia=("a", "b"), sequencia_cronologica=("10_PAUTA_1", "12_PAUTA_3"),
    )

    erros = validar_ground_truth([pergunta], IDS)

    assert any("sequencia_cronologica" in erro for erro in erros)


def test_longitudinal_valida():
    pergunta = _pergunta(
        categoria="longitudinal", itens_relevantes=("10_PAUTA_1", "11_PAUTA_2"),
        trechos_evidencia=("a", "b"), sequencia_cronologica=("10_PAUTA_1", "11_PAUTA_2"),
    )

    assert validar_ground_truth([pergunta], IDS) == []
