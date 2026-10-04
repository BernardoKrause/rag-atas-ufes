from app.geracao.prompt import FRASE_ABSTENCAO, montar_prompt
from app.geracao.tipos import EvidenciaNumerada, Fonte


def _evidencia(numero, texto, anterior=None, posterior=None, frases=None):
    return EvidenciaNumerada(
        numero=numero,
        fonte=Fonte(
            numero=numero,
            item_id_canonico=f"i{numero}",
            documento_id=1,
            rotulo=f"Ata X{numero}",
            trecho=texto,
            pagina=None,
        ),
        texto=texto,
        frases_grafo=frases or [],
        assunto_anterior=anterior,
        assunto_posterior=posterior,
    )


def test_sistema_contem_frase_de_abstencao_e_regra_de_citacao():
    sistema, _ = montar_prompt("pergunta?", [_evidencia(1, "t")])
    assert FRASE_ABSTENCAO in sistema
    assert "[n]" in sistema


def test_evidencias_aparecem_numeradas_na_ordem():
    _, usuario = montar_prompt(
        "pergunta?", [_evidencia(1, "primeiro"), _evidencia(2, "segundo")]
    )
    assert usuario.index("[1] Ata X1") < usuario.index("primeiro") < usuario.index(
        "[2] Ata X2"
    )
    assert usuario.index("[2] Ata X2") < usuario.index("segundo")


def test_frases_do_grafo_aparecem_na_evidencia():
    _, usuario = montar_prompt("p?", [_evidencia(1, "t", frases=["Departamento: DCC."])])
    assert "Departamento: DCC." in usuario


def test_vizinhos_aparecem_sem_numero_proprio():
    _, usuario = montar_prompt(
        "p?", [_evidencia(1, "t", anterior="Assunto A", posterior="Assunto B")]
    )
    assert "Item anterior na mesma ata, não citável: Assunto A" in usuario
    assert "Item posterior na mesma ata, não citável: Assunto B" in usuario
    assert "[2]" not in usuario


def test_vizinho_ausente_nao_gera_linha():
    _, usuario = montar_prompt("p?", [_evidencia(1, "t")])
    assert "não citável" not in usuario


def test_pergunta_vem_no_fim():
    _, usuario = montar_prompt("Qual o desfecho?", [_evidencia(1, "t")])
    assert usuario.endswith("Pergunta: Qual o desfecho?")
