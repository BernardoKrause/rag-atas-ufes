import json
from datetime import date

from app.geracao.eventos import Evento
from app.geracao.prompt import SISTEMA_RESPOSTA, montar_prompt, montar_prompt_resposta
from app.geracao.tipos import EvidenciaNumerada, Fonte


def _evidencia(numero, texto, anterior=None, posterior=None, frases=None, data=date(2025, 5, 13)):
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
        data_reuniao=data,
    )


def _registros(usuario):
    blocos = usuario.split("Evidências:\n", 1)[1].split("\n\nPergunta:", 1)[0]
    return [json.loads(linha) for linha in blocos.splitlines()]


def test_sistema_pede_um_registro_por_evidencia_em_json():
    sistema, _ = montar_prompt("pergunta?", [_evidencia(1, "t")])
    assert '"eventos"' in sistema
    assert '"relevante"' in sistema
    assert "cada evidência separadamente" in sistema


def test_sistema_pede_o_desfecho_registrado_no_fim_do_trecho():
    sistema, _ = montar_prompt("pergunta?", [_evidencia(1, "t")])
    assert "desfecho registrado" in sistema
    assert "fim do trecho" in sistema


def test_cada_evidencia_vira_um_registro_com_identificador_data_fonte_e_trecho():
    _, usuario = montar_prompt(
        "pergunta?",
        [_evidencia(1, "primeiro"), _evidencia(2, "segundo", data=date(2025, 5, 28))],
    )

    assert _registros(usuario) == [
        {"identificador": 1, "data_reuniao": "13/05/2025", "fonte": "Ata X1", "trecho": "primeiro"},
        {"identificador": 2, "data_reuniao": "28/05/2025", "fonte": "Ata X2", "trecho": "segundo"},
    ]


def test_frases_do_grafo_entram_no_registro():
    _, usuario = montar_prompt("p?", [_evidencia(1, "t", frases=["Departamento: DCC."])])
    assert _registros(usuario)[0]["relacoes"] == ["Departamento: DCC."]


def test_vizinhos_entram_como_contexto_nao_citavel():
    _, usuario = montar_prompt(
        "p?", [_evidencia(1, "t", anterior="Assunto A", posterior="Assunto B")]
    )
    registro = _registros(usuario)[0]
    assert registro["item_anterior_nao_citavel"] == "Assunto A"
    assert registro["item_posterior_nao_citavel"] == "Assunto B"


def test_campos_ausentes_nao_aparecem():
    _, usuario = montar_prompt("p?", [_evidencia(1, "t", data=None)])
    assert set(_registros(usuario)[0]) == {"identificador", "fonte", "trecho"}


def test_pergunta_vem_no_fim():
    _, usuario = montar_prompt("Qual o desfecho?", [_evidencia(1, "t")])
    assert usuario.endswith("Pergunta: Qual o desfecho?")


def _eventos_resposta(usuario):
    blocos = usuario.split("Eventos:\n", 1)[1].split("\n\nPergunta:", 1)[0]
    return [json.loads(linha) for linha in blocos.splitlines()]


def test_resposta_direta_recebe_os_eventos_validados_e_nao_os_trechos():
    evidencias = [
        _evidencia(1, "trecho longo", frases=["Departamento: DCC."], data=date(2025, 5, 28)),
        _evidencia(3, "outro trecho"),
    ]
    eventos = [Evento(3, "Excluiu da pauta."), Evento(1, "Aprovou o regimento.")]

    sistema, usuario = montar_prompt_resposta("Qual o desfecho?", eventos, evidencias)

    assert sistema == SISTEMA_RESPOSTA
    assert _eventos_resposta(usuario) == [
        {"identificador": 3, "data_reuniao": "13/05/2025", "descricao": "Excluiu da pauta."},
        {
            "identificador": 1, "data_reuniao": "28/05/2025", "descricao": "Aprovou o regimento.",
            "relacoes": ["Departamento: DCC."],
        },
    ]
    assert "trecho" not in usuario
    assert usuario.endswith("Pergunta: Qual o desfecho?")


def test_sistema_da_resposta_direta_exige_marcador():
    assert "[" in SISTEMA_RESPOSTA and "identificador" in SISTEMA_RESPOSTA
