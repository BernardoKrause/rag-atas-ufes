from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.geracao.tipos import EvidenciaNumerada, Fonte
from app.ingestion.segmentador import SOBREPOSICAO_FRAGMENTO
from app.models.documento import Documento, StatusAprovacao
from app.models.item_pauta import ItemPauta
from app.recuperacao.tipos import Evidencia

ROTULOS_GRAFO = [
    ("centro", "Centro"),
    ("departamento", "Departamento"),
    ("data_reuniao", "Data da reunião"),
    ("tipo_desfecho", "Desfecho"),
    ("resultado_votacao", "Resultado da votação"),
    ("ato_emitido", "Ato emitido"),
    ("encaminhamento", "Encaminhamento"),
]

ROTULOS_RELACAO = {
    "revoga": "Revoga",
    "altera": "Altera",
    "substitui": "Substitui",
    "revogado_por": "Revogado por",
    "alterado_por": "Alterado por",
    "substituido_por": "Substituído por",
    "trata_do_mesmo_assunto": "Trata do mesmo assunto que",
}


def frases_grafo(contexto_grafo: dict) -> list[str]:
    frases = [
        f"{rotulo}: {str(contexto_grafo[chave]).rstrip('. ')}."
        for chave, rotulo in ROTULOS_GRAFO
        if contexto_grafo.get(chave) is not None
    ]
    for relacao in contexto_grafo.get("deliberacoes_relacionadas", []):
        tipo = ROTULOS_RELACAO.get(relacao["tipo_relacao"], relacao["tipo_relacao"])
        alvo = relacao["ato_emitido"] or relacao["item_id_canonico"]
        frases.append(f"{tipo}: {alvo}.")
    return frases


def montar_rotulo(documento: Documento, item: ItemPauta) -> str:
    partes = [documento.orgao]
    if documento.numero_reuniao is not None:
        reuniao = f"{documento.numero_reuniao}ª reunião"
        if documento.tipo_reuniao:
            reuniao += f" {documento.tipo_reuniao.lower()}"
        partes.append(reuniao)
    partes.append(documento.data_reuniao.strftime("%d/%m/%Y"))
    partes.append(f"{item.secao.lower()}, item {item.numero_item}")
    if item.pagina_inicio is not None:
        partes.append(f"p. {item.pagina_inicio}")
    rotulo = "Ata " + ", ".join(partes)
    if documento.status_aprovacao == StatusAprovacao.PENDENTE_APROVACAO.value:
        rotulo += " (minuta em aprovação)"
    return rotulo


def _chave_item(item: ItemPauta) -> tuple[str, str, int]:
    return (item.secao, item.numero_item, item.ocorrencia_indice)


def buscar_vizinhos(sessao: Session, item: ItemPauta) -> tuple[str | None, str | None]:
    itens = sessao.execute(
        select(ItemPauta).where(ItemPauta.documento_id == item.documento_id).order_by(ItemPauta.id)
    ).scalars().all()
    chave = _chave_item(item)
    posicao = next(i for i, outro in enumerate(itens) if outro.id == item.id)
    anterior = next((o for o in reversed(itens[:posicao]) if _chave_item(o) != chave), None)
    posterior = next((o for o in itens[posicao + 1:] if _chave_item(o) != chave), None)
    return (
        anterior.assunto if anterior else None,
        posterior.assunto if posterior else None,
    )


def _juntar(partes: list[tuple[int, str]]) -> str:
    texto, indice_anterior = "", None
    for indice, parte in partes:
        if indice_anterior is None:
            texto = parte
        elif (
            indice == indice_anterior + 1
            and texto[-SOBREPOSICAO_FRAGMENTO:] == parte[:SOBREPOSICAO_FRAGMENTO]
        ):
            texto += parte[SOBREPOSICAO_FRAGMENTO:]
        else:
            texto += " […] " + parte
        indice_anterior = indice
    return texto


def _agrupar_fragmentos(evidencias, por_id) -> list[list[tuple[ItemPauta, Documento, Evidencia]]]:
    grupos: dict[tuple, list] = {}
    for evidencia in evidencias:
        if evidencia.item_id_canonico not in por_id:
            continue
        item, documento = por_id[evidencia.item_id_canonico]
        grupos.setdefault((item.documento_id, *_chave_item(item)), []).append(
            (item, documento, evidencia)
        )
    return [sorted(grupo, key=lambda membro: membro[0].fragmento_indice) for grupo in grupos.values()]


def montar_contexto(evidencias: list[Evidencia], sessao: Session) -> list[EvidenciaNumerada]:
    ids = [evidencia.item_id_canonico for evidencia in evidencias]
    linhas = sessao.execute(
        select(ItemPauta, Documento)
        .join(Documento, ItemPauta.documento_id == Documento.id_documento)
        .where(ItemPauta.item_id_canonico.in_(ids))
    ).all()
    por_id = {item.item_id_canonico: (item, documento) for item, documento in linhas}

    numeradas = []
    for grupo in _agrupar_fragmentos(evidencias, por_id):
        item, documento, _ = grupo[0]
        numero = len(numeradas) + 1
        anterior, posterior = buscar_vizinhos(sessao, item)
        frases = [f for _, _, e in grupo for f in frases_grafo(e.contexto_grafo)]
        numeradas.append(
            EvidenciaNumerada(
                numero=numero,
                fonte=Fonte(
                    numero=numero,
                    item_id_canonico=item.item_id_canonico,
                    documento_id=documento.id_documento,
                    rotulo=montar_rotulo(documento, item),
                    trecho=_juntar([(i.fragmento_indice, i.texto) for i, _, _ in grupo]),
                    pagina=item.pagina_inicio,
                ),
                texto=_juntar([(i.fragmento_indice, e.texto) for i, _, e in grupo]),
                frases_grafo=list(dict.fromkeys(frases)),
                assunto_anterior=anterior,
                assunto_posterior=posterior,
                data_reuniao=documento.data_reuniao,
            )
        )
    return numeradas
