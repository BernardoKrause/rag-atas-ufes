from datetime import date

from app.geracao.eventos import (
    Evento,
    desfecho_registrado,
    interpretar_eventos,
    ler_resposta_direta,
    montar_texto,
    termos_sem_apoio,
)

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


def test_desfecho_registrado_junta_votacao_e_ato_e_ignora_o_resto():
    frases = [
        "Centro: CCAE.", "Desfecho: Aprovado.", "Resultado da votação: Aprovado por unanimidade.",
        "Ato emitido: DECISAO_73_2025.", "Trata do mesmo assunto que: x.",
    ]
    assert desfecho_registrado(frases) == "Resultado da votação: Aprovado por unanimidade. Ato emitido: DECISAO_73_2025."


def test_desfecho_registrado_sem_frases_e_vazio():
    assert desfecho_registrado(["Centro: CCAE.", "Desfecho: Aprovado."]) == ""
    assert desfecho_registrado([]) == ""


def test_texto_anexa_o_desfecho_registrado_antes_do_marcador():
    eventos = [Evento(3, "Excluiu da pauta."), Evento(1, "Aprovou o regimento.")]
    desfechos = {1: "Resultado da votação: Aprovado por unanimidade."}

    assert montar_texto(eventos, DATAS, desfechos=desfechos) == (
        "13/05/2025: Excluiu da pauta. [3]\n"
        "28/05/2025: Aprovou o regimento. Resultado da votação: Aprovado por unanimidade. [1]"
    )


EVENTOS = [Evento(3, "Excluiu da pauta."), Evento(1, "Aprovou o regimento.")]


def test_resposta_direta_mantem_marcadores_dos_eventos():
    assert ler_resposta_direta('{"resposta": "Foi lotado no DCC [1]."}', EVENTOS) == "Foi lotado no DCC [1]."


def test_resposta_direta_sem_marcador_e_descartada_quando_ha_varios_eventos():
    assert ler_resposta_direta('{"resposta": "Foi lotado no DCC."}', EVENTOS) == ""


def test_resposta_direta_sem_marcador_recebe_o_do_unico_evento():
    eventos = [Evento(1, "Aprovou o regimento.")]
    assert ler_resposta_direta('{"resposta": "Foi lotado no DCC."}', eventos) == "Foi lotado no DCC [1]."


def test_resposta_direta_com_marcador_fora_dos_eventos_e_descartada():
    assert ler_resposta_direta('{"resposta": "Excluído [3] e aprovado [2]."}', EVENTOS) == ""
    assert ler_resposta_direta('{"resposta": "Aprovado [1, 2]."}', EVENTOS) == ""


def test_resposta_direta_que_repete_um_evento_e_descartada():
    assert ler_resposta_direta('{"resposta": "Aprovou o regimento [1]."}', EVENTOS) == ""


def test_resposta_direta_com_chaves_ou_quebra_de_linha_e_descartada():
    assert ler_resposta_direta('{"resposta": "{\\"x\\": 1} [1]"}', EVENTOS) == ""
    assert ler_resposta_direta('{"resposta": "Aprovado [1].\\nExcluído [3]."}', EVENTOS) == ""


def test_resposta_direta_invalida_ou_ausente_vira_vazio():
    assert ler_resposta_direta("DCC [1]", EVENTOS) == ""
    assert ler_resposta_direta('{"eventos": []}', EVENTOS) == ""
    assert ler_resposta_direta('{"resposta": 3}', EVENTOS) == ""
    assert ler_resposta_direta('{"resposta": "  "}', EVENTOS) == ""


def test_termo_da_pergunta_ausente_do_trecho_fica_sem_apoio():
    pergunta = "Qual foi a decisão sobre os PADs do Departamento de Artes Visuais (DAV), semestre 2024/2?"
    descricao = "Os PADs do Departamento de Artes Visuais (DAV) do semestre 2024/2 foram aprovados."
    trecho = "10) RADs de 2024.2 - Departamento de Comunicação Social. Aprovado a unanimidade."

    assert termos_sem_apoio(descricao, pergunta, trecho) == ["DAV", "Departamento de Artes Visuais"]


def test_semestre_da_pergunta_ausente_do_trecho_fica_sem_apoio():
    pergunta = "Quais datas foram definidas para o Calendário de Reuniões - Semestre 2024/1?"
    descricao = "As datas das reuniões do semestre 2024/1 foram: 24 de outubro."
    trecho = "3.2 Proposta de Calendário de Reuniões - Semestre 2024/2. Datas: 24 de outubro."

    assert termos_sem_apoio(descricao, pergunta, trecho) == ["2024/1"]


def test_termos_presentes_no_trecho_tem_apoio_mesmo_sem_acento():
    pergunta = "Qual foi a decisão sobre a disciplina COM10508 de Ciências da Computação?"
    descricao = "A redução de vagas da disciplina COM10508 de Ciências da Computação foi aprovada."
    trecho = "3.6 Reducao de vagas da disciplina COM10508 - curso de Ciencias da Computacao. Aprovado."

    assert termos_sem_apoio(descricao, pergunta, trecho) == []


def test_termo_que_nao_vem_da_pergunta_nao_e_conferido():
    pergunta = "Qual foi a decisão sobre os PADs no setor CAR?"
    descricao = "Os PADs do Departamento de Design foram aprovados."
    trecho = "PAD do DDesign. Aprovado."

    assert termos_sem_apoio(descricao, pergunta, trecho) == []


def test_palavra_comum_nao_e_termo_especifico():
    pergunta = "Que providências foram registradas sobre a licença da professora?"
    descricao = "A professora solicitou licença, homologada por unanimidade."
    trecho = "Licença para capacitação do Professor. Homologado por unanimidade."

    assert termos_sem_apoio(descricao, pergunta, trecho) == []
