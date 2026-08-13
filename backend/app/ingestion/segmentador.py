from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

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


RE_SECAO_NUMERADA = re.compile(
    r"(?<!\d)(\d{1,2})\.\s*("
    r"APR(?:OVA|ECIA)[CÇ][AÃ]O D[AE] ATAS?(?:/RELAT[OÓ]RIOS)?"
    r"|COMUNICA(?:[CÇ][AÃ]O|[CÇ][OÕ]ES)"
    r"|COMUNICADOS?"
    r"|EXPEDIENTE"
    r"|ORDEM DO DIA"
    r"|PAUTA"
    r"|INFORMES?"
    r"|PALAVRA[\s-]LIVRE"
    r")\s*[:.]"
)

_ALIAS_SECAO = {
    "APROVAÇÃO DA ATA": SECAO_APROVACAO_ATA,
    "APRECIAÇÃO DE ATA": SECAO_APROVACAO_ATA,
    "APRECIAÇÃO DE ATAS/RELATÓRIOS": SECAO_APROVACAO_ATA,
    "APROVAÇÃO DE ATA": SECAO_APROVACAO_ATA,
    "COMUNICAÇÃO": SECAO_COMUNICACOES,
    "COMUNICAÇÕES": SECAO_COMUNICACOES,
    "COMUNICADO": SECAO_COMUNICACOES,
    "COMUNICADOS": SECAO_COMUNICACOES,
    "EXPEDIENTE": SECAO_EXPEDIENTE,
    "ORDEM DO DIA": SECAO_ORDEM_DO_DIA,
    "PAUTA": SECAO_PAUTA,
    "INFORME": SECAO_INFORMES,
    "INFORMES": SECAO_INFORMES,
    "PALAVRA LIVRE": SECAO_PALAVRA_LIVRE,
    "PALAVRA-LIVRE": SECAO_PALAVRA_LIVRE,
}

# nao pode ser precedido/seguido de outro digito (evita casar o final de um
# token de anonimizacao tipo "PESSOA_12752") nem estar entre aspas (evita
# casar a citacao do numero de OUTRO item como referencia dentro do texto)
RE_ITEM_PONTILHADO = re.compile(r'(?<![\d"“])(\d{1,2}\.\d{1,2})(?!\d)\.?(?!["”])')


def detectar_itens_familia_pontilhada(texto_normalizado: str) -> list[ItemDetectado]:
    secoes = list(RE_SECAO_NUMERADA.finditer(texto_normalizado))
    itens: list[ItemDetectado] = []

    for i, secao_match in enumerate(secoes):
        numero_secao = secao_match.group(1)
        secao = _ALIAS_SECAO[secao_match.group(2)]
        inicio_corpo = secao_match.end()
        fim_corpo = secoes[i + 1].start() if i + 1 < len(secoes) else len(texto_normalizado)
        corpo = texto_normalizado[inicio_corpo:fim_corpo]

        matches_item = [
            m for m in RE_ITEM_PONTILHADO.finditer(corpo)
            if m.group(1).split(".")[0].lstrip("0") == numero_secao.lstrip("0")
        ]
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
# item sao a mesma passada, ao contrario da familia pontilhada
RE_ITEM_CT = re.compile(r"(?<!\d)(INFORME|PAUTA)\s+(\d{1,2}):(?!\d)")

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


RE_ITEM_CAR = re.compile(r"(?<!\d)(\d{1,2})\)(?!\d)")


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
    r"(EM PAUTA|COMUNICA(?:[CÇ][AÃ]O|[CÇ][OÕ]ES)|PROCESSOS/PROJETOS|PALAVRA LIVRE):"
)
RE_ITEM_CEFD = re.compile(r"(?<!\d)\[(\d{1,2})\](?!\d)")

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


# (tipo_orgao, centro) -> funcao detectora de itens sobre o texto normalizado.
# Mesmo estilo dict-driven de CENTRO_CAMPUS em extractor.py — variant sem
# entrada aqui levanta ValueError explicito, nunca falha silenciosamente.
CONFIG_VARIANTES: dict[tuple[str, str], Callable[[str], list[ItemDetectado]]] = {
    ("A", "*"): detectar_itens_familia_pontilhada,
    ("B", "CT"): detectar_itens_ct,
    ("B", "CAR"): detectar_itens_car,
    ("B", "CEFD"): detectar_itens_cefd,
    ("B", "CCAE"): detectar_itens_familia_pontilhada,
    ("B", "CE"): detectar_itens_familia_pontilhada,
    ("B", "CCHN"): detectar_itens_familia_pontilhada,
    ("C", "*"): detectar_itens_familia_pontilhada,
    ("D", "*"): detectar_itens_familia_pontilhada,
}


def _obter_detector(tipo_orgao: str, centro: str) -> Callable[[str], list[ItemDetectado]]:
    if (tipo_orgao, centro) in CONFIG_VARIANTES:
        return CONFIG_VARIANTES[(tipo_orgao, centro)]
    if (tipo_orgao, "*") in CONFIG_VARIANTES:
        return CONFIG_VARIANTES[(tipo_orgao, "*")]
    raise ValueError(f"variante sem detector mapeado: tipo_orgao={tipo_orgao!r} centro={centro!r}")


def segmentar_texto(tipo_orgao: str, centro: str, texto_limpo: str) -> list[ItemDetectado]:
    detector = _obter_detector(tipo_orgao, centro)

    texto_bruto = texto_limpo
    if tipo_orgao == "D":
        texto_bruto = _neutralizar_numeracao_de_margem(texto_bruto)

    texto_normalizado, _mapa = _normalizar_com_mapa(texto_bruto)
    itens = detector(texto_normalizado)
    return _reclassificar_exclusao_de_pauta(itens)


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
