from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.geracao.tipos import EvidenciaNumerada, Fonte
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
        f"{rotulo}: {contexto_grafo[chave]}."
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


def montar_contexto(evidencias: list[Evidencia], sessao: Session) -> list[EvidenciaNumerada]:
    ids = [evidencia.item_id_canonico for evidencia in evidencias]
    linhas = sessao.execute(
        select(ItemPauta, Documento)
        .join(Documento, ItemPauta.documento_id == Documento.id_documento)
        .where(ItemPauta.item_id_canonico.in_(ids))
    ).all()
    por_id = {item.item_id_canonico: (item, documento) for item, documento in linhas}

    numeradas = []
    for evidencia in evidencias:
        if evidencia.item_id_canonico not in por_id:
            continue
        item, documento = por_id[evidencia.item_id_canonico]
        numero = len(numeradas) + 1
        anterior, posterior = buscar_vizinhos(sessao, item)
        numeradas.append(
            EvidenciaNumerada(
                numero=numero,
                fonte=Fonte(
                    numero=numero,
                    item_id_canonico=item.item_id_canonico,
                    documento_id=documento.id_documento,
                    rotulo=montar_rotulo(documento, item),
                    trecho=item.texto,
                    pagina=item.pagina_inicio,
                ),
                texto=evidencia.texto,
                frases_grafo=frases_grafo(evidencia.contexto_grafo),
                assunto_anterior=anterior,
                assunto_posterior=posterior,
            )
        )
    return numeradas
