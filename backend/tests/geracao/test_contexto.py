from datetime import date

from app.geracao.contexto import buscar_vizinhos, frases_grafo, montar_contexto, montar_rotulo
from app.models.documento import StatusAprovacao
from app.recuperacao.tipos import Evidencia
from tests.recuperacao.conftest import criar_documento, criar_item


def _contexto_vazio(**overrides):
    base = dict(
        centro=None, departamento=None, data_reuniao=None, tipo_desfecho=None,
        resultado_votacao=None, ato_emitido=None, encaminhamento=None,
        deliberacoes_relacionadas=[],
    )
    base.update(overrides)
    return base


def _evidencia(item, rank):
    return Evidencia(
        item_id_canonico=item.item_id_canonico, texto=item.texto,
        contexto_grafo=_contexto_vazio(departamento="DCC"), rank_final=rank,
        scores={"lexico": None, "vetorial": None, "grafo": None},
    )


def test_frases_grafo_omite_campos_nulos():
    frases = frases_grafo(_contexto_vazio(departamento="DCC", tipo_desfecho="Aprovado"))
    assert frases == ["Departamento: DCC.", "Desfecho: Aprovado."]


def test_frases_grafo_inclui_relacoes_entre_deliberacoes():
    contexto = _contexto_vazio(
        deliberacoes_relacionadas=[
            {"tipo_relacao": "revoga", "item_id_canonico": "x", "ato_emitido": "RESOLUCAO_3_2020"},
            {"tipo_relacao": "alterado_por", "item_id_canonico": "y_pauta_2", "ato_emitido": None},
        ]
    )
    assert frases_grafo(contexto) == ["Revoga: RESOLUCAO_3_2020.", "Alterado por: y_pauta_2."]


def test_frases_grafo_vazio_devolve_lista_vazia():
    assert frases_grafo({}) == []


def test_montar_rotulo_completo(db_session):
    documento = criar_documento(
        db_session, nome_arquivo="rot_1.pdf", orgao="CT_DB", numero_reuniao=12,
        tipo_reuniao="Ordinária", data_reuniao=date(2025, 3, 4),
    )
    item = criar_item(db_session, documento, secao="PAUTA", numero_item="3", pagina_inicio=2)
    assert montar_rotulo(documento, item) == (
        "Ata CT_DB, 12ª reunião ordinária, 04/03/2025, pauta, item 3, p. 2"
    )


def test_montar_rotulo_omite_campos_nulos_e_marca_minuta(db_session):
    documento = criar_documento(
        db_session, nome_arquivo="rot_2.pdf", orgao="CAR", data_reuniao=date(2025, 1, 1),
        status_aprovacao=StatusAprovacao.PENDENTE_APROVACAO.value,
    )
    item = criar_item(db_session, documento, secao="ORDEM DO DIA", numero_item="1")
    assert montar_rotulo(documento, item) == (
        "Ata CAR, 01/01/2025, ordem do dia, item 1 (minuta em aprovação)"
    )


def test_buscar_vizinhos_traz_assunto_anterior_e_posterior(db_session):
    documento = criar_documento(db_session, nome_arquivo="viz_1.pdf")
    criar_item(db_session, documento, numero_item="1", assunto="Aprovação da ata anterior")
    meio = criar_item(db_session, documento, numero_item="2", assunto="Reforma do laboratório")
    criar_item(db_session, documento, numero_item="3", assunto="Calendário acadêmico")
    assert buscar_vizinhos(db_session, meio) == ("Aprovação da ata anterior", "Calendário acadêmico")


def test_buscar_vizinhos_primeiro_e_ultimo_item(db_session):
    documento = criar_documento(db_session, nome_arquivo="viz_2.pdf")
    primeiro = criar_item(db_session, documento, numero_item="1", assunto="A")
    ultimo = criar_item(db_session, documento, numero_item="2", assunto="B")
    assert buscar_vizinhos(db_session, primeiro) == (None, "B")
    assert buscar_vizinhos(db_session, ultimo) == ("A", None)


def test_buscar_vizinhos_pula_fragmentos_do_mesmo_item(db_session):
    documento = criar_documento(db_session, nome_arquivo="viz_3.pdf")
    criar_item(db_session, documento, numero_item="1", assunto="Anterior")
    fragmento_0 = criar_item(
        db_session, documento, numero_item="2", fragmento_indice=0, assunto="Longo",
        item_id_canonico="viz3_pauta_2",
    )
    criar_item(
        db_session, documento, numero_item="2", fragmento_indice=1, assunto="Longo",
        item_id_canonico="viz3_pauta_2_F1",
    )
    criar_item(db_session, documento, numero_item="3", assunto="Posterior")
    assert buscar_vizinhos(db_session, fragmento_0) == ("Anterior", "Posterior")


def test_montar_contexto_numera_na_ordem_e_monta_fontes(db_session):
    documento = criar_documento(db_session, nome_arquivo="ctx_1.pdf", orgao="CT_DB")
    item_a = criar_item(db_session, documento, numero_item="1", texto="texto A", assunto="A")
    item_b = criar_item(db_session, documento, numero_item="2", texto="texto B", assunto="B")

    numeradas = montar_contexto([_evidencia(item_b, 1), _evidencia(item_a, 2)], db_session)

    assert [e.numero for e in numeradas] == [1, 2]
    assert numeradas[0].fonte.item_id_canonico == item_b.item_id_canonico
    assert numeradas[0].fonte.numero == 1
    assert numeradas[0].fonte.documento_id == documento.id_documento
    assert numeradas[0].fonte.rotulo.startswith("Ata CT_DB, ")
    assert numeradas[0].texto == "texto B"
    assert numeradas[0].frases_grafo == ["Departamento: DCC."]
    assert (numeradas[0].assunto_anterior, numeradas[0].assunto_posterior) == ("A", None)


def test_montar_contexto_descarta_evidencia_sem_item_no_postgres(db_session):
    documento = criar_documento(db_session, nome_arquivo="ctx_2.pdf")
    item = criar_item(db_session, documento, numero_item="1")
    fantasma = Evidencia(
        item_id_canonico="nao_existe", texto="x", contexto_grafo={}, rank_final=1,
        scores={"lexico": None, "vetorial": None, "grafo": None},
    )

    numeradas = montar_contexto([fantasma, _evidencia(item, 2)], db_session)

    assert [(e.numero, e.fonte.item_id_canonico) for e in numeradas] == [(1, item.item_id_canonico)]
