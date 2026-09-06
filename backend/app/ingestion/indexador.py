from __future__ import annotations

import uuid
from dataclasses import dataclass

TAMANHO_JANELA = 120
SOBREPOSICAO_JANELA = 20

# fixo e arbitrario — so precisa ser estavel entre execucoes, nao tem
# significado alem de namespacear os UUID5 gerados por este modulo
NAMESPACE_INDEXADOR = uuid.UUID("cb1ba723-9f07-43ee-b6fa-107dd354bb04")


@dataclass(frozen=True)
class Janela:
    indice: int
    offset_inicio: int
    offset_fim: int
    token_ids: list[int]


def gerar_janelas(
    token_ids: list[int], tamanho_janela: int = TAMANHO_JANELA, sobreposicao: int = SOBREPOSICAO_JANELA
) -> list[Janela]:
    if not token_ids:
        return []

    passo = tamanho_janela - sobreposicao
    janelas = []
    inicio = 0
    indice = 0
    while True:
        fim = min(inicio + tamanho_janela, len(token_ids))
        janelas.append(Janela(indice=indice, offset_inicio=inicio, offset_fim=fim, token_ids=token_ids[inicio:fim]))
        if fim == len(token_ids):
            break
        inicio += passo
        indice += 1
    return janelas


def gerar_point_id(item_id_canonico: str, janela_indice: int) -> str:
    return str(uuid.uuid5(NAMESPACE_INDEXADOR, f"{item_id_canonico}_{janela_indice}"))
