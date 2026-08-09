from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata

from sqlalchemy import Sequence
from sqlalchemy.orm import Session
from transformers import pipeline

from app.models.documento import EntidadeAnonimizada, TipoEntidade

RE_PROCESSO_SIPAC = re.compile(r"23068\.\d{6}/\d{4}-\d{2}")

# nextval() e atomico entre execucoes concorrentes, mas nao e transacional —
# numeros podem ficar com buracos se uma insercao for revertida
SEQUENCIA_NUMERACAO_TOKEN = {
    TipoEntidade.PESSOA: Sequence("seq_entidades_anonimizadas_pessoa"),
    TipoEntidade.PROCESSO: Sequence("seq_entidades_anonimizadas_processo"),
}

MODELO_NER = "Gpaiva/NERDE-base"

# o tokenizer do NERDE-base nao declara model_max_length, entao a pipeline
# nao trunca sozinha — sem essa janela, uma ata inteira estoura o limite real
# de 512 posicoes do BERT. Contagem em tokens, nao caracteres: a razao
# caractere/token varia demais em texto juridico denso pra um corte por
# caracteres garantir a margem.
LARGURA_JANELA_NER_TOKENS = 400
SOBREPOSICAO_JANELA_NER_TOKENS = 50

_ner_pipeline = None


def _carregar_ner():
    global _ner_pipeline
    if _ner_pipeline is None:
        _ner_pipeline = pipeline(
            "token-classification", model=MODELO_NER, aggregation_strategy="simple"
        )
    return _ner_pipeline


def _janelas_para_ner(texto: str, tokenizer) -> list[tuple[int, str]]:
    """Corta pela tokenizacao real do modelo, nao por contagem de caracteres,
    pra nunca estourar o limite de tokens do BERT. A sobreposicao garante que
    um nome cortado no fim de uma janela apareca inteiro na seguinte."""
    offsets = tokenizer(texto, return_offsets_mapping=True, add_special_tokens=False)[
        "offset_mapping"
    ]
    if len(offsets) <= LARGURA_JANELA_NER_TOKENS:
        return [(0, texto)]

    janelas = []
    inicio_token = 0
    while True:
        fim_token = min(inicio_token + LARGURA_JANELA_NER_TOKENS, len(offsets))
        inicio_char = offsets[inicio_token][0]
        fim_char = offsets[fim_token - 1][1]
        janelas.append((inicio_char, texto[inicio_char:fim_char]))
        if fim_token == len(offsets):
            break
        inicio_token = fim_token - SOBREPOSICAO_JANELA_NER_TOKENS
    return janelas


def _mesclar_intervalos(intervalos: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Mescla intervalos sobrepostos/adjacentes: cobre tanto a mesma entidade
    detectada em janelas vizinhas quanto um nome que aparece fragmentado numa
    janela e inteiro na outra."""
    intervalos = sorted(intervalos)
    mesclados: list[tuple[int, int]] = []
    for inicio, fim in intervalos:
        if mesclados and inicio <= mesclados[-1][1]:
            mesclados[-1] = (mesclados[-1][0], max(mesclados[-1][1], fim))
        else:
            mesclados.append((inicio, fim))
    return mesclados


def _subtrair_intervalo(
    alvo: tuple[int, int], remover: tuple[int, int]
) -> list[tuple[int, int]]:
    inicio, fim = alvo
    r_inicio, r_fim = remover
    if r_fim <= inicio or r_inicio >= fim:
        return [(inicio, fim)]

    pedacos = []
    if inicio < r_inicio:
        pedacos.append((inicio, r_inicio))
    if fim > r_fim:
        pedacos.append((r_fim, fim))
    return pedacos


def _recortar_sobreposicao_com_processos(
    intervalos_pessoa: list[tuple[int, int]],
    intervalos_processo: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Numeros de processo SIPAC vem de regex exato; nomes vem de NER, cujos
    limites podem errar (ex.: "Silva23068.001234/2025-11" sem espaco no PDF).
    Recorta do span de PESSOA a parte que cai dentro de um span de
    PROCESSO."""
    ajustados: list[tuple[int, int]] = []
    for inicio, fim in intervalos_pessoa:
        pedacos = [(inicio, fim)]
        for p_inicio, p_fim in intervalos_processo:
            pedacos = [
                pedaco
                for i, f in pedacos
                for pedaco in _subtrair_intervalo((i, f), (p_inicio, p_fim))
            ]
        ajustados.extend(pedacos)
    return ajustados


def _achar_entidades_pessoa(texto: str) -> list[tuple[int, int]]:
    ner = _carregar_ner()
    intervalos: list[tuple[int, int]] = []
    for offset, janela in _janelas_para_ner(texto, ner.tokenizer):
        for entidade in ner(janela):
            if entidade["entity_group"] != "PER":
                continue
            intervalos.append((offset + entidade["start"], offset + entidade["end"]))
    return _mesclar_intervalos(intervalos)


def _normalizar_entidade(texto: str) -> str:
    texto = unicodedata.normalize("NFKC", texto)
    return " ".join(texto.upper().split())


def _gerar_hash_entidade(secret_key: bytes, tipo: TipoEntidade, texto_bruto: str) -> str:
    mensagem = f"{tipo.value}:{_normalizar_entidade(texto_bruto)}".encode()
    return hmac.new(secret_key, mensagem, hashlib.sha256).hexdigest()


def _obter_ou_criar_token(
    sessao: Session, secret_key: bytes, tipo: TipoEntidade, texto_bruto: str
) -> str:
    hash_entidade = _gerar_hash_entidade(secret_key, tipo, texto_bruto)

    existente = (
        sessao.query(EntidadeAnonimizada)
        .filter_by(hash_entidade=hash_entidade)
        .one_or_none()
    )
    if existente is not None:
        return existente.token

    numero = sessao.scalar(SEQUENCIA_NUMERACAO_TOKEN[tipo])
    token = f"{tipo.value.upper()}_{numero:04d}"
    sessao.add(
        EntidadeAnonimizada(hash_entidade=hash_entidade, tipo=tipo.value, token=token)
    )
    sessao.flush()
    return token


def anonimizar_texto(texto: str, secret_key: bytes, sessao: Session) -> str:
    """Substitui pessoas (NER) e numeros de processo SIPAC (regex) por tokens
    deterministicos, consultando/gravando EntidadeAnonimizada — a mesma pessoa
    ou processo real sempre gera o mesmo token, inclusive entre atas e execucoes
    diferentes."""
    intervalos_processo = [(m.start(), m.end()) for m in RE_PROCESSO_SIPAC.finditer(texto)]
    intervalos_pessoa = _recortar_sobreposicao_com_processos(
        _achar_entidades_pessoa(texto), intervalos_processo
    )

    ocorrencias: list[tuple[int, int, TipoEntidade]] = [
        (inicio, fim, TipoEntidade.PESSOA) for inicio, fim in intervalos_pessoa
    ]
    ocorrencias += [
        (inicio, fim, TipoEntidade.PROCESSO) for inicio, fim in intervalos_processo
    ]

    # ordem decrescente de inicio: substituir do fim pro comeco preserva os
    # indices das ocorrencias ainda nao processadas
    ocorrencias.sort(key=lambda o: o[0], reverse=True)

    resultado = texto
    for inicio, fim, tipo in ocorrencias:
        token = _obter_ou_criar_token(sessao, secret_key, tipo, texto[inicio:fim])
        resultado = resultado[:inicio] + token + resultado[fim:]

    return resultado
