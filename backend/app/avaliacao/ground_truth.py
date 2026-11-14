from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

CATEGORIAS = ("intra_exata", "intra_reformulada", "inter_atas", "longitudinal", "sem_evidencia")
ORIGENS = ("servidor", "autor")
CAMPOS_LISTA = ("itens_relevantes", "trechos_evidencia", "sequencia_cronologica")
CAMPOS_TEXTO = (
    "id", "categoria", "origem", "pergunta", "resposta_referencia", "tipo_dificuldade", "observacao",
)


@dataclass(frozen=True)
class PerguntaReferencia:
    id: str
    categoria: str
    origem: str
    pergunta: str
    resposta_referencia: str
    itens_relevantes: tuple[str, ...]
    trechos_evidencia: tuple[str, ...]
    sequencia_cronologica: tuple[str, ...]
    tipo_dificuldade: str
    observacao: str


def carregar_ground_truth(caminho: Path) -> list[PerguntaReferencia]:
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    perguntas = []
    for bruta in dados.get("perguntas") or []:
        campos = {nome: str(bruta.get(nome) or "") for nome in CAMPOS_TEXTO}
        campos.update({nome: tuple(str(v) for v in bruta.get(nome) or ()) for nome in CAMPOS_LISTA})
        perguntas.append(PerguntaReferencia(**campos))
    return perguntas


def _documento(item_id: str) -> str:
    return item_id.split("_", 1)[0]


def _erros_da_pergunta(p: PerguntaReferencia, ids_logicos: set[str]) -> list[str]:
    erros = []
    if p.categoria not in CATEGORIAS:
        erros.append(f"{p.id}: categoria inválida {p.categoria!r}")
    if p.origem not in ORIGENS:
        erros.append(f"{p.id}: origem inválida {p.origem!r}")
    if not p.pergunta.strip():
        erros.append(f"{p.id}: pergunta vazia")
    if not p.resposta_referencia.strip():
        erros.append(f"{p.id}: resposta_referencia vazia")
    for item_id in p.itens_relevantes:
        if item_id not in ids_logicos:
            erros.append(f"{p.id}: item {item_id} não existe ou não é item lógico")
    if len(p.trechos_evidencia) != len(p.itens_relevantes):
        erros.append(f"{p.id}: trechos_evidencia e itens_relevantes com tamanhos diferentes")

    if p.categoria == "sem_evidencia":
        if p.itens_relevantes:
            erros.append(f"{p.id}: sem_evidencia não pode ter itens_relevantes")
        return erros
    if p.categoria in ("intra_exata", "intra_reformulada") and len(p.itens_relevantes) != 1:
        erros.append(f"{p.id}: {p.categoria} exige exatamente 1 item")
    if p.categoria in ("inter_atas", "longitudinal"):
        if len({_documento(i) for i in p.itens_relevantes}) < 2:
            erros.append(f"{p.id}: {p.categoria} exige itens de pelo menos 2 atas")
    if p.categoria == "longitudinal":
        sequencia = p.sequencia_cronologica
        if len(sequencia) < 2 or not set(sequencia) <= set(p.itens_relevantes):
            erros.append(f"{p.id}: sequencia_cronologica precisa de 2+ itens dentre os relevantes")
    return erros


def validar_ground_truth(perguntas: list[PerguntaReferencia], ids_logicos: set[str]) -> list[str]:
    erros = []
    vistos = set()
    for pergunta in perguntas:
        if pergunta.id in vistos:
            erros.append(f"{pergunta.id}: id repetido")
        vistos.add(pergunta.id)
        erros.extend(_erros_da_pergunta(pergunta, ids_logicos))
    return erros
