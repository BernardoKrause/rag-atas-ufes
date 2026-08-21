from __future__ import annotations

import re
import unicodedata
from bisect import bisect_right
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta

TAMANHO_MAX_FRAGMENTO = 3000
SOBREPOSICAO_FRAGMENTO = 300

SECAO_APROVACAO_ATA = "APROVAÇÃO DE ATA"
SECAO_COMUNICACOES = "COMUNICAÇÕES"
SECAO_EXPEDIENTE = "EXPEDIENTE"
SECAO_EXCLUSAO_DE_PAUTA = "EXCLUSÃO DE PAUTA"
SECAO_ORDEM_DO_DIA = "ORDEM DO DIA"
SECAO_PAUTA = "PAUTA"
SECAO_INFORMES = "INFORMES"
SECAO_PALAVRA_LIVRE = "PALAVRA LIVRE"
SECAO_PROCESSOS_PROJETOS = "PROCESSOS/PROJETOS"


@dataclass(frozen=True)
class ItemDetectado:
    secao: str
    numero_item: str
    inicio: int  # offset no texto normalizado
    fim: int  # offset no texto normalizado
    texto: str


def _normalizar_com_mapa(texto: str) -> tuple[str, list[int]]:
    """Colapsa qualquer sequencia de espaco em branco (incluindo quebras de
    linha — alguns modelos de ata, ex. CT, tem uma palavra por linha) num
    unico espaco, preservando um mapa de cada indice do texto normalizado
    pro indice correspondente no texto original. Necessario pro segmentador
    continuar sabendo em que pagina do PDF cada item cai depois de
    normalizar — normalizar sem preservar o mapa perderia essa
    correspondencia."""
    partes: list[str] = []
    mapa: list[int] = []
    em_espaco = False
    for i, ch in enumerate(texto):
        if ch.isspace():
            em_espaco = True
            continue
        if em_espaco:
            if partes:
                partes.append(" ")
                mapa.append(i)
            em_espaco = False
        partes.append(ch)
        mapa.append(i)
    return "".join(partes), mapa


# grupos nomeados em vez de um dict alias->secao casado pelo texto literal
# capturado: o alias por texto exigia enumerar toda combinacao de
# prefixo/acento/singular-plural que o regex reconhece (ex.: "APRECIAÇÃO DA
# ATA" bate no regex mas nao tinha entrada no dict antigo -> KeyError). Cada
# alternativa abaixo ja mapeia 1:1 pra uma secao, entao o grupo nomeado que
# casou entrega a secao diretamente, sem depender do texto exato casado.
# o lookahead do terminador (abaixo) e protecao parcial: defende contra um
# match coincidental "N. PALAVRA-DE-SECAO" que NAO tem subitem "N.M" logo em
# seguida (ver test_familia_pontilhada_nao_trunca_secao_em_numero_coincidente_no_meio_da_frase),
# mas nao contra um match coincidental que POR ACASO e seguido de algum texto
# "N.M"-shaped nao relacionado (ex. "43. COMUNICADOS 12.5 do plano" faria
# "43. COMUNICADOS" passar pelo lookahead como se fosse cabecalho valido).
# Confirmado ausente do corpus real dos 357 docs (validacao da Tarefa 7), mas
# nao e estruturalmente impossivel — o teste citado acima cobre so o caso sem
# subitem seguinte, nao este.
RE_SECAO_NUMERADA = re.compile(
    r"(?<!\d)(\d{1,2})\.\s*(?:"
    r"(?P<aprovacao_ata>APR(?:OVA|ECIA)[CÇ][AÃ]O D[AE] ATAS?(?:/RELAT[OÓ]RIOS)?)"
    r"|(?P<comunicacoes>COMUNICA(?:[CÇ][AÃ]O|[CÇ][OÕ]ES)|COMUNICADOS?)"
    r"|(?P<expediente>EXPEDIENTE)"
    r"|(?P<ordem_do_dia>ORDEM DO DIA)"
    r"|(?P<pauta>PAUTAS?)"
    r"|(?P<informes>INFORMES?)"
    r"|(?P<palavra_livre>PALAVRA[\s-]LIVRE)"
    r")\s*(?:[:.]|(?=\s?\d{1,2}\.\d))",
    re.IGNORECASE,
)

_SECAO_POR_GRUPO = {
    "aprovacao_ata": SECAO_APROVACAO_ATA,
    "comunicacoes": SECAO_COMUNICACOES,
    "expediente": SECAO_EXPEDIENTE,
    "ordem_do_dia": SECAO_ORDEM_DO_DIA,
    "pauta": SECAO_PAUTA,
    "informes": SECAO_INFORMES,
    "palavra_livre": SECAO_PALAVRA_LIVRE,
}


def _secao_do_match(secao_match: re.Match) -> str:
    nome_grupo = secao_match.lastgroup
    return _SECAO_POR_GRUPO[nome_grupo]

# nao pode ser precedido/seguido de outro digito (evita casar o final de um
# token de anonimizacao tipo "PESSOA_12752") nem estar entre aspas (evita
# casar a citacao do numero de OUTRO item como referencia dentro do texto)
RE_ITEM_PONTILHADO = re.compile(r'(?<![\d"“])(\d{1,2}\.\d{1,2})(?!\d)\.?(?!["”])')


def detectar_itens_familia_pontilhada(texto_normalizado: str) -> list[ItemDetectado]:
    secoes = list(RE_SECAO_NUMERADA.finditer(texto_normalizado))
    itens: list[ItemDetectado] = []

    for i, secao_match in enumerate(secoes):
        numero_secao = secao_match.group(1)
        secao = _secao_do_match(secao_match)
        inicio_corpo = secao_match.end()
        fim_corpo = secoes[i + 1].start() if i + 1 < len(secoes) else len(texto_normalizado)
        corpo = texto_normalizado[inicio_corpo:fim_corpo]

        matches_item = [
            m for m in RE_ITEM_PONTILHADO.finditer(corpo)
            if m.group(1).split(".")[0].lstrip("0") == numero_secao.lstrip("0")
        ]
        for j, item_match in enumerate(matches_item):
            inicio_item = inicio_corpo if j == 0 else inicio_corpo + item_match.start()
            fim_item = (
                inicio_corpo + matches_item[j + 1].start()
                if j + 1 < len(matches_item)
                else fim_corpo
            )
            itens.append(
                ItemDetectado(
                    secao=secao,
                    numero_item=item_match.group(1),
                    inicio=inicio_item,
                    fim=fim_item,
                    texto=texto_normalizado[inicio_item:fim_item].strip(),
                )
            )

    return itens


# Tipo D tem numeracao de linha na margem esquerda (rastreabilidade de
# correcoes) — o PyMuPDF extrai cada numero de margem como sua propria
# "linha" de texto, intercalado com o conteudo real (ex.: "1. APRECIAÇÃO DE\n8\nATA:").
# Substituir por espacos do mesmo tamanho (nao remover) preserva os offsets
# originais — necessario pro mapeamento de pagina continuar correto.
RE_NUMERACAO_MARGEM = re.compile(r"(?m)^[ \t]*\d{1,3}[ \t]*$\n?")


def _neutralizar_numeracao_de_margem(texto: str) -> str:
    return RE_NUMERACAO_MARGEM.sub(lambda m: " " * len(m.group(0)), texto)


def _reclassificar_exclusao_de_pauta(itens: list[ItemDetectado]) -> list[ItemDetectado]:
    """EXCLUSÃO DE PAUTA aparece como subtitulo textual dentro do EXPEDIENTE
    (nao tem numeracao propria de secao) — vira sua propria secao quando o
    texto do item comeca literalmente com esse subtitulo."""
    resultado = []
    for item in itens:
        if item.secao == SECAO_EXPEDIENTE and item.texto.upper().startswith("EXCLUSÃO DE PAUTA"):
            resultado.append(
                ItemDetectado(SECAO_EXCLUSAO_DE_PAUTA, item.numero_item, item.inicio, item.fim, item.texto)
            )
        else:
            resultado.append(item)
    return resultado


# CT (B1) nao tem uma secao "PAUTA" com subitens dentro — cada item ja e
# "PAUTA N:" ou "INFORME N:" diretamente, entao a deteccao de secao e de
# item sao a mesma passada, ao contrario da familia pontilhada.
# Guarda contra aspas nas duas pontas (mesmo motivo do RE_ITEM_PONTILHADO):
# evita casar a citacao do numero de OUTRO item como referencia no texto.
RE_ITEM_CT = re.compile(r'(?<!\d)(?<!["“])(INFORME|PAUTA)\s+(\d{1,2}):(?!\d)(?!["”])')

_SECAO_CT = {"INFORME": SECAO_INFORMES, "PAUTA": SECAO_PAUTA}


def detectar_itens_ct(texto_normalizado: str) -> list[ItemDetectado]:
    matches = list(RE_ITEM_CT.finditer(texto_normalizado))
    itens = []
    for i, m in enumerate(matches):
        inicio = m.start()
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(texto_normalizado)
        itens.append(
            ItemDetectado(
                secao=_SECAO_CT[m.group(1)],
                numero_item=m.group(2),
                inicio=inicio,
                fim=fim,
                texto=texto_normalizado[inicio:fim].strip(),
            )
        )
    return itens


# mesma guarda de aspas do RE_ITEM_PONTILHADO/RE_ITEM_CT
RE_ITEM_CAR = re.compile(r'(?<![\d"“])(\d{1,2})\)(?!\d)(?!["”])')


def detectar_itens_car(texto_normalizado: str) -> list[ItemDetectado]:
    """CAR (B2) nao numera a secao de informes (fica vazia/implicita — ver
    edge case de secao sem itens detectaveis); todos os itens caem direto
    em PAUTA, numerados sem padding fixo ("1)", "04)", "6)"...)."""
    indice_pauta = texto_normalizado.find("PAUTA:")
    if indice_pauta == -1:
        return []

    corpo = texto_normalizado[indice_pauta + len("PAUTA:"):]
    matches = list(RE_ITEM_CAR.finditer(corpo))
    itens = []
    for i, m in enumerate(matches):
        inicio = m.start()
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(corpo)
        itens.append(
            ItemDetectado(
                secao=SECAO_PAUTA,
                numero_item=m.group(1),
                inicio=indice_pauta + len("PAUTA:") + inicio,
                fim=indice_pauta + len("PAUTA:") + fim,
                texto=corpo[inicio:fim].strip(),
            )
        )
    return itens


# CEFD tem vocabulario de secao proprio, fora do documentado no §7 original
# (EM PAUTA em vez de PAUTA; PROCESSOS/PROJETOS nao tem equivalente em
# nenhum outro variant) — descoberto na investigacao empirica da pendencia 3
RE_SECAO_CEFD = re.compile(
    r"(EM PAUTA|COMUNICA(?:[CÇ][AÃ]O|[CÇ][OÕ]ES)|PROCESSOS/PROJETOS|PALAVRA LIVRE)[:.]"
)
# mesma guarda de aspas do RE_ITEM_PONTILHADO/RE_ITEM_CT
RE_ITEM_CEFD = re.compile(r'(?<![\d"“])\[(\d{1,2})\](?!\d)(?!["”])')

_SECAO_CEFD = {
    "EM PAUTA": SECAO_PAUTA,
    "COMUNICAÇÃO": SECAO_COMUNICACOES,
    "COMUNICAÇÕES": SECAO_COMUNICACOES,
    "PROCESSOS/PROJETOS": SECAO_PROCESSOS_PROJETOS,
    "PALAVRA LIVRE": SECAO_PALAVRA_LIVRE,
}


def detectar_itens_cefd(texto_normalizado: str) -> list[ItemDetectado]:
    secoes = list(RE_SECAO_CEFD.finditer(texto_normalizado))
    itens = []
    for i, secao_match in enumerate(secoes):
        secao = _SECAO_CEFD[secao_match.group(1)]
        inicio_corpo = secao_match.end()
        fim_corpo = secoes[i + 1].start() if i + 1 < len(secoes) else len(texto_normalizado)
        corpo = texto_normalizado[inicio_corpo:fim_corpo]

        matches_item = list(RE_ITEM_CEFD.finditer(corpo))
        for j, item_match in enumerate(matches_item):
            inicio_item = inicio_corpo + item_match.start()
            fim_item = (
                inicio_corpo + matches_item[j + 1].start()
                if j + 1 < len(matches_item)
                else fim_corpo
            )
            itens.append(
                ItemDetectado(
                    secao=secao,
                    numero_item=item_match.group(1),
                    inicio=inicio_item,
                    fim=fim_item,
                    texto=texto_normalizado[inicio_item:fim_item].strip(),
                )
            )
    return itens


# CCE nao usa cabecalho de secao (PAUTA:/INFORME:) nem numeracao pontilhada
# — cada assunto e um "Ponto N" (ou, em atas mais antigas, a ordem invertida
# "Nº. Ponto") direto apos o texto de abertura/quorum, sem distincao de
# secao. Reuniao de assunto unico usa "Ponto único" em vez de numero.
# Maiusculas/minusculas variam entre atas de anos diferentes — daí IGNORECASE
# em vez da guarda de aspas usada nos outros detectores (aqui a citacao
# narrativa de um ponto ja votado nao usa aspas, ver achado (c) CCE — tratado
# via ocorrencia_indice em segmentar_e_persistir, nao aqui).
# O grupo numerico aceita uma parte decimal opcional "(?:\.\d{1,2})?" porque
# atas reais (doc 683 do corpus) tem cabecalhos proprios "Ponto 8.3"/"Ponto
# 8.4" com a palavra "Ponto" repetida antes de cada subitem — sem o grupo
# decimal, o "\.?" sozinho nunca consome o ponto (faria a lookahead (?!\d)
# falhar contra o digito seguinte), entao o match parava em "8" e colidia
# "Ponto 8"/"Ponto 8.3"/"Ponto 8.4" sob numero_item="8". O grupo decimal so
# ativa quando ha digito colado logo apos o ponto — nao afeta "Ponto 4."
# de sentenca comum nem os casos, tambem reais (docs 643/668/682), em que
# "Ponto N" e repetido e o subitem "N.M" aparece solto mais adiante SEM a
# palavra "Ponto" antes (ali o "PONTO" literal nunca fica colado ao ".M",
# entao o regex so casa o "N" de cada vez — colisao genuina de repeticao,
# nao truncamento decimal, ja tratada via ocorrencia_indice).
RE_ITEM_CCE = re.compile(
    r"(?<!\d)(?:"
    r"PONTO\s+(?:(\d{1,2}(?:\.\d{1,2})?)|(ÚNICO))\.?"
    r"|(\d{1,2})[ºo°]\.?\s*PONTO"
    r")(?!\d)",
    re.IGNORECASE,
)


def detectar_itens_cce(texto_normalizado: str) -> list[ItemDetectado]:
    matches = list(RE_ITEM_CCE.finditer(texto_normalizado))
    itens = []
    for i, m in enumerate(matches):
        numero_item = "1" if m.group(2) else (m.group(1) or m.group(3))
        inicio = m.start()
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(texto_normalizado)
        itens.append(
            ItemDetectado(
                secao=SECAO_PAUTA,
                numero_item=numero_item,
                inicio=inicio,
                fim=fim,
                texto=texto_normalizado[inicio:fim].strip(),
            )
        )
    return itens


# CE tipo D (Colegiado de Pedagogia) nao numera a secao (ao contrario da
# familia pontilhada) e usa item de nivel unico ("1. Texto", nao "1.1") sem
# vinculo com nenhum numero de secao — descoberto na investigacao empirica
# do gap de 77 docs. Mas o MESMO colegiado tambem tem atas mais antigas (ex.
# fixture da 3a reuniao, formato pontilhado "1. APRECIACAO DE ATA: 1.1 ...")
# que usam o formato pontilhado padrao — ("D","CE") nao e um variant unico,
# e o dict de dispatch so tem uma chave por (tipo_orgao, centro), entao a
# escolha entre os dois formatos precisa acontecer dentro da funcao, pelo
# conteudo do texto — ao contrario do RE_ITEM_CCE, que resolve sua propria
# variacao de formato antiga/nova dentro do proprio regex via alternancia
# (sem precisar de discriminador externo), aqui os dois formatos (pontilhado
# vs. nivel unico) nao compartilham vocabulario de cabecalho suficiente pra
# unificar num regex so — o discriminador de formato precisa ser o resultado
# de outro detector (detectar_itens_familia_pontilhada), chamado como
# fallback dentro de detectar_itens_ce_d.
# Sem re.IGNORECASE e com \b: cabecalho real e sempre "INFORMES:"/"PAUTA."
# em CAIXA ALTA nos dois docs reais (463/469) — texto narrativo comum tipo
# "Retirado de pauta." / "Retirado de Pauta." (ambos confirmados nos dois
# docs reais) bate em minuscula/capitalizado mas nao em caixa alta, entao
# case-sensitive sozinho ja filtra; \b e so uma guarda extra de fronteira.
RE_SECAO_CE_D = re.compile(r"\b(INFORMES?|PAUTA)[:.]")
# mesma guarda de aspas de entrada dos outros detectores (lookbehind); a
# guarda de saida e dispensavel aqui porque o lookahead de maiuscula/ordinal
# logo em seguida ja a subsome (uma aspa de fechamento nao e maiuscula nem
# ordinal, entao ja fica fora do match sem precisar de guarda separada).
# Mais guarda de barra: sem ela, notacao de data/semestre "DD/MM." ou "AAAA/N." (ex.
# "2021/2. A professora...", "02/11. Ferias...") bate igualzinho no padrao
# digito-ponto-espaco-maiuscula e vira item fantasma — confirmado nos dois
# docs reais (463/469) durante a validacao empirica deste detector. A guarda
# de aspas so cobre o caractere imediatamente antes do digito, nao o span
# inteiro entre aspas — uma lista numerada citada dentro de uma unica frase
# entre aspas (ex. doc 463, item 3 da PAUTA: “1. Responder... 2. Registrar
# no campo de sugestões...”) ainda pode gerar um item fantasma a partir do
# segundo numero em diante, ja que so o primeiro vem colado na aspa de
# abertura. Achado real, aceito como limitacao conhecida (ocorrencia unica
# nos dois docs, blast radius contido, nao gera colisao de PK gracas ao
# ocorrencia_indice em segmentar_e_persistir).
# O lookahead aceita maiuscula direto (item comum) OU numero ordinal seguido
# de "o"/"a" (ex. "5a Conferencia...") — tambem confirmado em doc 463, onde
# um item real comeca com ordinal em vez de maiuscula. \s* (nao \s+): doc
# 463 item 4 e "4.Metodologia..." sem espaco (artefato de extracao de PDF,
# confirmado via scan de \d{1,2}\.[A-ZÀ-Ú] nos dois docs reais) — a guarda
# contra numeracao de dois niveis ("4.1") continua vindo do lookbehind (nao
# pode ser precedido de digito/ponto/aspas/barra) e do proprio requisito de
# maiuscula/ordinal logo em seguida, nao do espaco em si.
RE_ITEM_CE_D = re.compile(r'(?<![\d."“/])(\d{1,2})\.\s*(?=[A-ZÀ-Ú]|\d{1,2}[ºª])')

_SECAO_CE_D = {"INFORME": SECAO_INFORMES, "INFORMES": SECAO_INFORMES, "PAUTA": SECAO_PAUTA}


def detectar_itens_ce_d(texto_normalizado: str) -> list[ItemDetectado]:
    # tenta primeiro o formato pontilhado padrao (mesmo usado pelo resto da
    # familia B/C/D): e a fixture real da 3a reuniao (mesmo colegiado, ata
    # mais antiga) que define a ordem seguranca aqui — o resultado NAO-VAZIO
    # de detectar_itens_familia_pontilhada e o sinal confiavel de "formato
    # antigo"; um resultado vazio do detector novo (RE_SECAO_CE_D/RE_ITEM_CE_D)
    # NAO e confiavel como sinal equivalente pro formato novo, porque
    # cabecalhos de secao pontilhados ("2. EXPEDIENTE:", "3. INFORMES:", "4.
    # PAUTA:") tambem casam parcialmente no RE_ITEM_CE_D e podem produzir
    # itens espurios em vez de lista vazia dependendo de onde caem os
    # limites de secao — confirmado por review: bastou um "5. PALAVRA
    # LIVRE:" extra na mesma fixture pra fazer o detector novo devolver 1
    # item espurio em vez de lista vazia, o que quebraria esse discriminador
    # se a ordem fosse invertida.
    itens_pontilhados = detectar_itens_familia_pontilhada(texto_normalizado)
    if itens_pontilhados:
        return itens_pontilhados

    secoes = list(RE_SECAO_CE_D.finditer(texto_normalizado))
    itens = []
    for i, secao_match in enumerate(secoes):
        secao = _SECAO_CE_D[secao_match.group(1).upper()]
        inicio_corpo = secao_match.end()
        fim_corpo = secoes[i + 1].start() if i + 1 < len(secoes) else len(texto_normalizado)
        corpo = texto_normalizado[inicio_corpo:fim_corpo]

        matches_item = list(RE_ITEM_CE_D.finditer(corpo))
        for j, item_match in enumerate(matches_item):
            inicio_item = inicio_corpo + item_match.start()
            fim_item = (
                inicio_corpo + matches_item[j + 1].start()
                if j + 1 < len(matches_item)
                else fim_corpo
            )
            itens.append(
                ItemDetectado(
                    secao=secao,
                    numero_item=item_match.group(1),
                    inicio=inicio_item,
                    fim=fim_item,
                    texto=texto_normalizado[inicio_item:fim_item].strip(),
                )
            )
    return itens


# (tipo_orgao, centro) -> funcao detectora de itens sobre o texto normalizado.
# Mesmo estilo dict-driven de CENTRO_CAMPUS em extractor.py — variant sem
# entrada aqui levanta ValueError explicito, nunca falha silenciosamente.
CONFIG_VARIANTES: dict[tuple[str, str], Callable[[str], list[ItemDetectado]]] = {
    ("A", "*"): detectar_itens_familia_pontilhada,
    ("A", "CEUNES"): detectar_itens_ct,
    ("B", "CT"): detectar_itens_ct,
    ("B", "CAR"): detectar_itens_car,
    ("B", "CEFD"): detectar_itens_cefd,
    ("B", "CCAE"): detectar_itens_familia_pontilhada,
    ("B", "CE"): detectar_itens_familia_pontilhada,
    ("B", "CCHN"): detectar_itens_familia_pontilhada,
    ("B", "CEUNES"): detectar_itens_ct,
    ("B", "CCE"): detectar_itens_cce,
    ("C", "*"): detectar_itens_familia_pontilhada,
    ("D", "CE"): detectar_itens_ce_d,
    ("D", "*"): detectar_itens_familia_pontilhada,
}


def _obter_detector(tipo_orgao: str, centro: str) -> Callable[[str], list[ItemDetectado]]:
    if (tipo_orgao, centro) in CONFIG_VARIANTES:
        return CONFIG_VARIANTES[(tipo_orgao, centro)]
    if (tipo_orgao, "*") in CONFIG_VARIANTES:
        return CONFIG_VARIANTES[(tipo_orgao, "*")]
    raise ValueError(f"variante sem detector mapeado: tipo_orgao={tipo_orgao!r} centro={centro!r}")


def segmentar_texto(tipo_orgao: str, centro: str, texto_limpo: str) -> tuple[list[ItemDetectado], list[int]]:
    """Retorna os itens detectados junto com o mapa de offsets (indice no
    texto normalizado -> indice no texto_limpo original), pra quem precisar
    localizar a posicao original de um item (ex.: mapeamento de pagina) nao
    ter que reimplementar a mesma normalizacao."""
    detector = _obter_detector(tipo_orgao, centro)

    texto_bruto = texto_limpo
    if tipo_orgao == "D":
        texto_bruto = _neutralizar_numeracao_de_margem(texto_bruto)

    texto_normalizado, mapa = _normalizar_com_mapa(texto_bruto)
    itens = detector(texto_normalizado)
    return _reclassificar_exclusao_de_pauta(itens), mapa


def dividir_fragmentos(texto: str) -> list[str]:
    """Heuristica por caracteres, nao pelo tokenizer real do modelo de
    embedding (Parte 5 ainda nao escolheu o modelo). Mesmo estilo de janela
    com sobreposicao ja usado em _janelas_para_ner (cleaner.py)."""
    if len(texto) <= TAMANHO_MAX_FRAGMENTO:
        return [texto]

    fragmentos = []
    inicio = 0
    while True:
        fim = min(inicio + TAMANHO_MAX_FRAGMENTO, len(texto))
        fragmentos.append(texto[inicio:fim])
        if fim == len(texto):
            break
        inicio = fim - SOBREPOSICAO_FRAGMENTO
    return fragmentos


def mapear_pagina(offset: int, paginas_offsets: list[int] | None) -> int | None:
    """paginas_offsets[i] e o offset de inicio da pagina i (0-based) no
    texto — bisect_right conta quantos inicios de pagina sao <= offset, que
    e diretamente o numero de pagina 1-based."""
    if not paginas_offsets:
        return None
    return bisect_right(paginas_offsets, offset)


def _slug_secao(secao: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", secao).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Z0-9]+", "_", sem_acento.upper()).strip("_")


def gerar_item_id_canonico(
    documento_id: int, secao: str, numero_item: str, ocorrencia_indice: int, fragmento_indice: int
) -> str:
    base = f"{documento_id}_{_slug_secao(secao)}_{numero_item}"
    if ocorrencia_indice > 0:
        base = f"{base}_D{ocorrencia_indice}"
    if fragmento_indice > 0:
        return f"{base}_F{fragmento_indice}"
    return base


def segmentar_e_persistir(documento: Documento, sessao: Session) -> list[ItemPauta]:
    """Idempotente por documento_id: substitui (delete + insert) os itens
    daquele documento a cada rerun, em vez de tentar um upsert campo a
    campo — mais simples e evita deixar itens obsoletos quando um rerun
    produz menos itens que o anterior (ex.: ajuste de regex).

    ocorrencia_indice desambigua itens que compartilham (secao, numero_item)
    dentro do mesmo documento — numeracao duplicada na fonte ou falso
    positivo de deteccao (numero citado dentro do corpo de outro item) nao
    quebram mais a constraint unica; ficam persistidos lado a lado, com
    sufixo "_D{n}" no item_id_canonico, pra revisao manual amostral."""
    itens_detectados, mapa = segmentar_texto(documento.tipo_orgao, documento.centro, documento.texto_limpo)

    sessao.execute(delete(ItemPauta).where(ItemPauta.documento_id == documento.id_documento))

    contador_ocorrencias: dict[tuple[str, str], int] = {}
    novos_itens = []
    for item in itens_detectados:
        chave = (item.secao, item.numero_item)
        ocorrencia_indice = contador_ocorrencias.get(chave, 0)
        contador_ocorrencias[chave] = ocorrencia_indice + 1

        fragmentos = dividir_fragmentos(item.texto)
        offset_original_inicio = mapa[item.inicio] if item.inicio < len(mapa) else mapa[-1]
        offset_original_fim = mapa[item.fim - 1] if 0 <= item.fim - 1 < len(mapa) else mapa[-1]

        for indice_fragmento, texto_fragmento in enumerate(fragmentos):
            novos_itens.append(
                ItemPauta(
                    documento_id=documento.id_documento,
                    item_id_canonico=gerar_item_id_canonico(
                        documento.id_documento, item.secao, item.numero_item,
                        ocorrencia_indice, indice_fragmento,
                    ),
                    secao=item.secao,
                    numero_item=item.numero_item,
                    ocorrencia_indice=ocorrencia_indice,
                    fragmento_indice=indice_fragmento,
                    texto=texto_fragmento,
                    pagina_inicio=mapear_pagina(offset_original_inicio, documento.paginas_offsets),
                    pagina_fim=mapear_pagina(offset_original_fim, documento.paginas_offsets),
                )
            )

    sessao.add_all(novos_itens)
    sessao.flush()
    return novos_itens


def main() -> None:
    engine = create_engine(settings.database_url)
    Sessao = sessionmaker(bind=engine)

    with Sessao() as sessao:
        documentos = sessao.execute(select(Documento)).scalars().all()
        total_itens = 0
        for documento in documentos:
            itens = segmentar_e_persistir(documento, sessao)
            sessao.commit()
            total_itens += len(itens)
        print(f"{len(documentos)} documentos processados, {total_itens} itens de pauta gerados.")


if __name__ == "__main__":
    main()
