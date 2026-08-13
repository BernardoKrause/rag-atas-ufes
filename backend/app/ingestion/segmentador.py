from __future__ import annotations

import re
from dataclasses import dataclass

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
