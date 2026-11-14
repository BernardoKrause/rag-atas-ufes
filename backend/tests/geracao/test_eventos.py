from datetime import date

from app.geracao.eventos import Evento, interpretar_eventos, ler_resposta_direta, montar_texto

DATAS = {1: date(2025, 5, 28), 2: date(2024, 8, 1), 3: date(2025, 5, 13)}


def test_interpreta_json_cercado_por_bloco_de_codigo():
    saida = '```json\n{"eventos": [{"evidencia": 1, "relevante": true, "descricao": "Aprovou o regimento."}]}\n```'

    assert interpretar_eventos(saida, DATAS) == [Evento(1, "Aprovou o regimento.")]


def test_ordena_eventos_pela_data_da_reuniao():
    saida = (
        '{"eventos": ['
        '{"evidencia": 1, "relevante": true, "descricao": "Aprovou."},'
        '{"evidencia": 3, "relevante": true, "descricao": "Excluiu da pauta."}]}'
    )

    eventos = interpretar_eventos(saida, DATAS)

    assert [e.evidencia for e in eventos] == [3, 1]


def test_descarta_irrelevantes_identificadores_fora_do_contexto_e_descricao_vazia():
    saida = (
        '{"eventos": ['
        '{"evidencia": 2, "relevante": false, "descricao": ""},'
        '{"evidencia": 9, "relevante": true, "descricao": "Inventado."},'
        '{"evidencia": "1", "relevante": true, "descricao": "  "},'
        '{"evidencia": 3, "relevante": true, "descricao": "Excluiu da pauta."}]}'
    )

    assert interpretar_eventos(saida, DATAS) == [Evento(3, "Excluiu da pauta.")]


def test_aceita_identificador_como_texto_numerico():
    saida = '{"eventos": [{"evidencia": "3", "relevante": true, "descricao": "Excluiu da pauta."}]}'

    assert interpretar_eventos(saida, DATAS) == [Evento(3, "Excluiu da pauta.")]


def test_remove_marcadores_que_o_modelo_poe_na_descricao():
    saida = '{"eventos": [{"evidencia": 1, "relevante": true, "descricao": "Aprovou o regimento [1]."}]}'

    assert interpretar_eventos(saida, DATAS) == [Evento(1, "Aprovou o regimento.")]


def test_junta_eventos_de_varios_objetos_seguidos():
    saida = (
        '{"eventos": [{"evidencia": 1, "relevante": true, "descricao": "Aprovou."}]}\n\n'
        '{"eventos": [{"evidencia": 3, "relevante": true, "descricao": "Excluiu da pauta."}]}'
    )

    assert [e.evidencia for e in interpretar_eventos(saida, DATAS)] == [3, 1]


def test_saida_que_nao_e_json_devolve_none():
    assert interpretar_eventos("O conselho aprovou [1].", DATAS) is None
    assert interpretar_eventos('{"eventos": "nada"}', DATAS) is None


def test_lista_vazia_devolve_lista_vazia():
    assert interpretar_eventos('{"eventos": []}', DATAS) == []


def test_texto_traz_data_descricao_e_marcador_por_linha():
    eventos = [Evento(3, "Excluiu da pauta."), Evento(1, "Aprovou o regimento.")]

    assert montar_texto(eventos, DATAS) == (
        "13/05/2025: Excluiu da pauta. [3]\n28/05/2025: Aprovou o regimento. [1]"
    )


def test_resposta_direta_vem_antes_dos_eventos():
    eventos = [Evento(3, "Excluiu da pauta."), Evento(1, "Aprovou o regimento.")]

    assert montar_texto(eventos, DATAS, "O tema passou por duas reuniões.") == (
        "O tema passou por duas reuniões.\n\n"
        "13/05/2025: Excluiu da pauta. [3]\n28/05/2025: Aprovou o regimento. [1]"
    )


def test_le_resposta_direta_sem_marcadores():
    assert ler_resposta_direta('{"resposta": "DCC [1]."}') == "DCC."


def test_resposta_direta_invalida_ou_ausente_vira_vazio():
    assert ler_resposta_direta("DCC") == ""
    assert ler_resposta_direta('{"eventos": []}') == ""
    assert ler_resposta_direta('{"resposta": 3}') == ""
