from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import lru_cache

import torch
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from transformers import AutoModel, AutoTokenizer, PreTrainedModel, PreTrainedTokenizerBase

from app.core.config import settings

TAMANHO_JANELA = 120
SOBREPOSICAO_JANELA = 20

COLLECTION = "itens_pauta"
DIMENSAO_EMBEDDING = 768

NOME_MODELO = "PORTULAN/serafim-100m-portuguese-pt-sentence-encoder-ir"

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


def obter_cliente_qdrant() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url)


def garantir_collection(cliente: QdrantClient) -> None:
    if cliente.collection_exists(COLLECTION):
        return
    cliente.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=DIMENSAO_EMBEDDING, distance=Distance.COSINE),
    )


@lru_cache(maxsize=1)
def carregar_modelo() -> tuple[PreTrainedTokenizerBase, PreTrainedModel]:
    tokenizer = AutoTokenizer.from_pretrained(NOME_MODELO)
    modelo = AutoModel.from_pretrained(NOME_MODELO)
    modelo.eval()
    return tokenizer, modelo


def tokenizar_texto(tokenizer: PreTrainedTokenizerBase, texto: str) -> list[int]:
    return tokenizer(texto, add_special_tokens=False)["input_ids"]


def gerar_embedding(tokenizer: PreTrainedTokenizerBase, modelo: PreTrainedModel, token_ids: list[int]) -> list[float]:
    entrada = [tokenizer.cls_token_id] + token_ids + [tokenizer.sep_token_id]
    tensor_ids = torch.tensor([entrada])
    tensor_mask = torch.ones_like(tensor_ids)

    with torch.no_grad():
        saida = modelo(input_ids=tensor_ids, attention_mask=tensor_mask)

    embeddings_token = saida.last_hidden_state[0]
    mascara = tensor_mask[0].unsqueeze(-1).float()
    media = (embeddings_token * mascara).sum(dim=0) / mascara.sum()
    normalizado = media / media.norm()
    return normalizado.tolist()
