from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata

from sqlalchemy.orm import Session
from transformers import pipeline

from app.models.documento import EntidadeAnonimizada, TipoEntidade

RE_PROCESSO_SIPAC = re.compile(r"23068\.\d{6}/\d{4}-\d{2}")

MODELO_NER = "Gpaiva/NERDE-base"

# margem segura de caracteres por janela: a config do tokenizer do NERDE-base
# nao declara model_max_length (fica no default gigante da lib), entao a
# pipeline nao trunca sozinha — sem isso, uma ata inteira (milhares de tokens)
# estoura o limite real de 512 posicoes do BERT por baixo dos panos
LARGURA_JANELA_NER = 1500
SOBREPOSICAO_JANELA_NER = 200

_ner_pipeline = None


def _carregar_ner():
    global _ner_pipeline
    if _ner_pipeline is None:
        _ner_pipeline = pipeline(
            "token-classification", model=MODELO_NER, aggregation_strategy="simple"
        )
    return _ner_pipeline


def _janelas_para_ner(texto: str) -> list[tuple[int, str]]:
    """Divide o texto em janelas sobrepostas de caracteres, cada uma bem abaixo
    do limite de tokens do BERT. A sobreposicao garante que um nome cortado no
    fim de uma janela apareca inteiro na janela seguinte."""
    if len(texto) <= LARGURA_JANELA_NER:
        return [(0, texto)]

    janelas = []
    inicio = 0
    while True:
        fim = min(inicio + LARGURA_JANELA_NER, len(texto))
        janelas.append((inicio, texto[inicio:fim]))
        if fim == len(texto):
            break
        inicio = fim - SOBREPOSICAO_JANELA_NER
    return janelas


def _mesclar_intervalos(intervalos: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Mescla intervalos sobrepostos/adjacentes — cobre tanto a mesma entidade
    detectada duas vezes (zona de sobreposicao entre janelas) quanto um nome
    cortado que aparece como fragmento numa janela e inteiro na vizinha."""
    intervalos = sorted(intervalos)
    mesclados: list[tuple[int, int]] = []
    for inicio, fim in intervalos:
        if mesclados and inicio <= mesclados[-1][1]:
            mesclados[-1] = (mesclados[-1][0], max(mesclados[-1][1], fim))
        else:
            mesclados.append((inicio, fim))
    return mesclados


def _achar_entidades_pessoa(texto: str) -> list[tuple[int, int]]:
    ner = _carregar_ner()
    intervalos: list[tuple[int, int]] = []
    for offset, janela in _janelas_para_ner(texto):
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

    numero = sessao.query(EntidadeAnonimizada).filter_by(tipo=tipo.value).count() + 1
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
    ocorrencias: list[tuple[int, int, TipoEntidade]] = [
        (inicio, fim, TipoEntidade.PESSOA) for inicio, fim in _achar_entidades_pessoa(texto)
    ]
    ocorrencias += [
        (m.start(), m.end(), TipoEntidade.PROCESSO)
        for m in RE_PROCESSO_SIPAC.finditer(texto)
    ]

    # ordem decrescente de inicio: substituir do fim pro comeco preserva os
    # indices das ocorrencias ainda nao processadas
    ocorrencias.sort(key=lambda o: o[0], reverse=True)

    resultado = texto
    for inicio, fim, tipo in ocorrencias:
        token = _obter_ou_criar_token(sessao, secret_key, tipo, texto[inicio:fim])
        resultado = resultado[:inicio] + token + resultado[fim:]

    return resultado
