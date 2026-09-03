from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.texto import slugificar
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
    inicio: int
    fim: int
    texto: str


def _normalizar_com_mapa(texto: str) -> tuple[str, list[int]]:
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

        preambulo = corpo[:matches_item[0].start()] if matches_item else corpo
        secao_primeiro_item = (
            SECAO_EXCLUSAO_DE_PAUTA
            if secao == SECAO_EXPEDIENTE and preambulo.strip().upper().startswith("EXCLUSÃO DE PAUTA")
            else secao
        )

        for j, item_match in enumerate(matches_item):
            inicio_item = (
                inicio_corpo if j == 0 and secao == SECAO_APROVACAO_ATA
                else inicio_corpo + item_match.start()
            )
            fim_item = (
                inicio_corpo + matches_item[j + 1].start()
                if j + 1 < len(matches_item)
                else fim_corpo
            )
            itens.append(
                ItemDetectado(
                    secao=secao_primeiro_item if j == 0 else secao,
                    numero_item=item_match.group(1),
                    inicio=inicio_item,
                    fim=fim_item,
                    texto=texto_normalizado[inicio_item:fim_item].strip(),
                )
            )

    return itens


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


RE_ITEM_CAR = re.compile(r'(?<![\d"“])(\d{1,2})\)(?!\d)(?!["”])')


def detectar_itens_car(texto_normalizado: str) -> list[ItemDetectado]:
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


RE_SECAO_CEFD = re.compile(
    r"(EM PAUTA|COMUNICA(?:[CÇ][AÃ]O|[CÇ][OÕ]ES)|PROCESSOS/PROJETOS|PALAVRA LIVRE)[:.]"
)
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


RE_SECAO_CE_D = re.compile(r"\b(INFORMES?|PAUTA)[:.]")
RE_ITEM_CE_D = re.compile(r'(?<![\d."“/])(\d{1,2})\.\s*(?=[A-ZÀ-Ú]|\d{1,2}[ºª])')

_SECAO_CE_D = {"INFORME": SECAO_INFORMES, "INFORMES": SECAO_INFORMES, "PAUTA": SECAO_PAUTA}


def detectar_itens_ce_d(texto_normalizado: str) -> list[ItemDetectado]:
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
    detector = _obter_detector(tipo_orgao, centro)

    texto_normalizado, mapa = _normalizar_com_mapa(texto_limpo)
    itens = detector(texto_normalizado)
    return itens, mapa


def dividir_fragmentos(texto: str) -> list[str]:
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
    if not paginas_offsets:
        return None
    return bisect_right(paginas_offsets, offset)


def gerar_item_id_canonico(
    documento_id: int, secao: str, numero_item: str, ocorrencia_indice: int, fragmento_indice: int
) -> str:
    base = f"{documento_id}_{slugificar(secao)}_{numero_item}"
    if ocorrencia_indice > 0:
        base = f"{base}_D{ocorrencia_indice}"
    if fragmento_indice > 0:
        return f"{base}_F{fragmento_indice}"
    return base


def segmentar_e_persistir(documento: Documento, sessao: Session) -> list[ItemPauta]:
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
