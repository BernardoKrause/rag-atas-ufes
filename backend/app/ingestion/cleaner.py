from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata
from bisect import bisect_left
from itertools import accumulate

from sqlalchemy import Sequence
from sqlalchemy.orm import Session
from transformers import pipeline

from app.models.documento import EntidadeAnonimizada, TipoEntidade

# formato geral de protocolo NNNNN.NNNNNN/NNNN-NN — cobre SIPAC-UFES
# (prefixo 23068.) e outros orgaos com o mesmo padrao (ex.: achado (f),
# protocolo Fala.BR/CGU 23546. no doc 462 do corpus real)
RE_NUMERO_PROCESSO = re.compile(r"\d{5}\.\d{6}/\d{4}-\d{2}")

RE_CPF = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")

# proximidade da palavra "RG": nao ha formato nacional unico de RG, entao a
# deteccao e por contexto (palavra-chave) em vez de regex solto — validado
# contra o corpus real (342 documentos) sem nenhum falso positivo
RE_RG = re.compile(r"\bRG[:\s]{1,4}[\d]{1,2}\.?\d{3}\.?\d{3}-?[\dxX]\b", re.IGNORECASE)

RE_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

# enderecos institucionais/de funcao confirmados no corpus real — nao
# identificam uma pessoa, entao ficam fora da anonimizacao. Qualquer
# endereco novo desse tipo achado depois deve ser adicionado aqui.
EMAILS_INSTITUCIONAIS = frozenset({
    "cchn.ufes@gmail.com",
    "direcao.cceufes@gmail.com",
    "secretaria.ct@ufes.br",
    "sud.ccens@ufes.br",
    "departamento.computacaoeeletronica.saomateus@ufes.br",
    "notificacao@astenassinatura.com.br",
})

# nextval() e atomico entre execucoes concorrentes, mas nao e transacional —
# numeros podem ficar com buracos se uma insercao for revertida
SEQUENCIA_NUMERACAO_TOKEN = {
    TipoEntidade.PESSOA: Sequence("seq_entidades_anonimizadas_pessoa"),
    TipoEntidade.PROCESSO: Sequence("seq_entidades_anonimizadas_processo"),
    TipoEntidade.CPF: Sequence("seq_entidades_anonimizadas_cpf"),
    TipoEntidade.RG: Sequence("seq_entidades_anonimizadas_rg"),
    TipoEntidade.EMAIL: Sequence("seq_entidades_anonimizadas_email"),
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


def _recortar_sobreposicao(
    intervalos_pessoa: list[tuple[int, int]],
    *outros_intervalos: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Numeros de processo e e-mail vem de regex exato; nomes vem de NER,
    cujos limites podem errar (ex.: "Silva23068.001234/2025-11" ou
    "marcus.v.almeida@ufes.br" sem espaco no PDF). Recorta do span de PESSOA
    a parte que cai dentro de qualquer span protegido (processo, e-mail...)."""
    ajustados = list(intervalos_pessoa)
    for intervalos in outros_intervalos:
        proximo: list[tuple[int, int]] = []
        for inicio, fim in ajustados:
            pedacos = [(inicio, fim)]
            for o_inicio, o_fim in intervalos:
                pedacos = [
                    pedaco
                    for i, f in pedacos
                    for pedaco in _subtrair_intervalo((i, f), (o_inicio, o_fim))
                ]
            proximo.extend(pedacos)
        ajustados = proximo
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


def anonimizar_texto(
    texto: str, secret_key: bytes, sessao: Session
) -> tuple[str, list[tuple[int, int]]]:
    """Substitui pessoas (NER), numeros de processo, CPF, RG e e-mail pessoal
    (regex) por tokens deterministicos, consultando/gravando
    EntidadeAnonimizada — a mesma pessoa ou processo real sempre gera o mesmo
    token, inclusive entre atas e execucoes diferentes.

    Alem do texto anonimizado, retorna a lista de substituicoes (offset
    original, delta de tamanho) em ordem crescente de offset — o token tem
    tamanho fixo, diferente do nome/processo real que substitui, entao quem
    tiver offsets calculados sobre o texto original (ex.: paginas_offsets)
    precisa dessa lista pra reprojeta-los via remapear_offsets()."""
    intervalos_processo = [(m.start(), m.end()) for m in RE_NUMERO_PROCESSO.finditer(texto)]
    intervalos_email = [
        (m.start(), m.end())
        for m in RE_EMAIL.finditer(texto)
        if m.group(0).lower() not in EMAILS_INSTITUCIONAIS
    ]
    intervalos_cpf = [(m.start(), m.end()) for m in RE_CPF.finditer(texto)]
    intervalos_rg = [(m.start(), m.end()) for m in RE_RG.finditer(texto)]

    intervalos_pessoa = _recortar_sobreposicao(
        _achar_entidades_pessoa(texto), intervalos_processo, intervalos_email
    )

    ocorrencias: list[tuple[int, int, TipoEntidade]] = [
        (inicio, fim, TipoEntidade.PESSOA) for inicio, fim in intervalos_pessoa
    ]
    ocorrencias += [(inicio, fim, TipoEntidade.PROCESSO) for inicio, fim in intervalos_processo]
    ocorrencias += [(inicio, fim, TipoEntidade.EMAIL) for inicio, fim in intervalos_email]
    ocorrencias += [(inicio, fim, TipoEntidade.CPF) for inicio, fim in intervalos_cpf]
    ocorrencias += [(inicio, fim, TipoEntidade.RG) for inicio, fim in intervalos_rg]

    # ordem decrescente de inicio: substituir do fim pro comeco preserva os
    # indices das ocorrencias ainda nao processadas
    ocorrencias.sort(key=lambda o: o[0], reverse=True)

    resultado = texto
    substituicoes: list[tuple[int, int]] = []
    for inicio, fim, tipo in ocorrencias:
        token = _obter_ou_criar_token(sessao, secret_key, tipo, texto[inicio:fim])
        resultado = resultado[:inicio] + token + resultado[fim:]
        substituicoes.append((inicio, len(token) - (fim - inicio)))

    substituicoes.sort(key=lambda s: s[0])
    return resultado, substituicoes


def remapear_offsets(offsets: list[int], substituicoes: list[tuple[int, int]]) -> list[int]:
    """Reprojeta offsets calculados sobre o texto pre-anonimizacao pro
    espaco do texto pos-anonimizacao (o retornado por anonimizar_texto),
    somando o delta acumulado de toda substituicao que ocorreu antes de cada
    offset. Uma substituicao que comeca exatamente NO offset ainda nao o
    deslocou — ela desloca o que vem depois de si mesma."""
    if not substituicoes:
        return list(offsets)

    inicios = [inicio for inicio, _delta in substituicoes]
    deltas_acumulados = list(accumulate(delta for _inicio, delta in substituicoes))

    resultado = []
    for offset in offsets:
        indice = bisect_left(inicios, offset)
        delta = deltas_acumulados[indice - 1] if indice > 0 else 0
        resultado.append(offset + delta)
    return resultado
