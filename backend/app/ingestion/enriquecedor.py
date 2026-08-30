from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Callable

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.texto import remover_acentos_maiusculo, slugificar
from app.ingestion._extenso import parse_cardinal, tokenizar
from app.ingestion.segmentador import (
    RE_ITEM_CAR, RE_ITEM_CCE, RE_ITEM_CE_D, RE_ITEM_CEFD, RE_ITEM_CT, RE_ITEM_PONTILHADO,
)
from app.models.consultas import carregar_documentos_com_itens
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta


@dataclass(frozen=True)
class CamposEnriquecidos:
    assunto: str | None
    tipo_desfecho: str | None
    resultado_votacao: str | None
    encaminhamento: str | None
    ato_emitido: str | None
    departamento_origem: str | None


_MARCADORES_ITEM = [RE_ITEM_CT, RE_ITEM_CAR, RE_ITEM_CEFD, RE_ITEM_CCE, RE_ITEM_CE_D, RE_ITEM_PONTILHADO]

# fórmula padrão de encerramento de ata ("Nada mais havendo a tratar, ...
# sera aprovada e assinada por todos os membros"). Sem marcador de proximo
# item pra cortar, o ultimo item de cada ata carrega esse boilerplate junto
# no seu texto — e ele proprio contem palavras-chave de desfecho ("aprovada")
# que nao tem nada a ver com a votacao do item. Achado em 194/357 documentos
# do corpus real.
RE_ENCERRAMENTO_ATA = re.compile(r"Nada\s+mais\s+havendo\s+a\s+tratar", re.IGNORECASE)


def extrair_corpo_sem_marcador(secao: str, texto: str) -> str:
    """O marcador de abertura do item (ex. "PAUTA 2:", "4.3", "[3]") sempre
    casa no offset 0 de item.texto — mesmo regex usado pelo segmentador.py
    pra achar o inicio do item. Tenta cada marcador conhecido nessa posicao;
    se nenhum casar (nao deveria acontecer pra um item ja segmentado), retorna
    o texto integral."""
    for marcador in _MARCADORES_ITEM:
        match = marcador.match(texto)
        if match:
            texto = texto[match.end():]
            break

    match_encerramento = RE_ENCERRAMENTO_ATA.search(texto)
    if match_encerramento:
        texto = texto[:match_encerramento.start()]

    return texto.strip()


CONFIG_ENRIQUECEDOR: dict[tuple[str, str], Callable[[str, date], CamposEnriquecidos]] = {}


def _obter_extrator(tipo_orgao: str, centro: str) -> Callable[[str, date], CamposEnriquecidos]:
    if (tipo_orgao, centro) in CONFIG_ENRIQUECEDOR:
        return CONFIG_ENRIQUECEDOR[(tipo_orgao, centro)]
    if (tipo_orgao, "*") in CONFIG_ENRIQUECEDOR:
        return CONFIG_ENRIQUECEDOR[(tipo_orgao, "*")]
    raise ValueError(f"variante sem extrator mapeado: tipo_orgao={tipo_orgao!r} centro={centro!r}")


def enriquecer_item(tipo_orgao: str, centro: str, item_texto: str, data_reuniao: date) -> CamposEnriquecidos:
    extrator = _obter_extrator(tipo_orgao, centro)
    return extrator(item_texto, data_reuniao)


def enriquecer_e_persistir(documento: Documento, itens: list[ItemPauta], sessao: Session) -> None:
    for item in itens:
        campos = enriquecer_item(documento.tipo_orgao, documento.centro, item.texto, documento.data_reuniao)
        item.assunto = campos.assunto
        item.tipo_desfecho = campos.tipo_desfecho
        item.resultado_votacao = campos.resultado_votacao
        item.encaminhamento = campos.encaminhamento
        item.ato_emitido = campos.ato_emitido
        item.departamento_origem = campos.departamento_origem
    sessao.flush()


RE_DECISAO_CT = re.compile(r"Decis[ãa]o:\s*([A-ZÀ-Ú][a-zà-ú]+)\(?a?\)?\.?\s*(.*)", re.DOTALL)
RE_DEPARTAMENTO_CT = re.compile(r"-\s*Departamento de ([^-.:]+?)\s*[-.:]")

LIMITE_DEPARTAMENTO_ORIGEM = 60

_DESFECHO_CT = {
    "APROVADO": "Aprovado", "HOMOLOGADO": "Aprovado", "REPROVADO": "Reprovado",
    "RETIRADO": "Retirado", "ADIADO": "Adiado", "ENCAMINHADO": "Encaminhado",
}


def _normalizar_departamento(bruto: str) -> str | None:
    normalizado = slugificar(bruto)
    if len(normalizado) > LIMITE_DEPARTAMENTO_ORIGEM:
        return None
    return normalizado or None


def extrair_ct(texto: str, data_reuniao: date) -> CamposEnriquecidos:
    corpo = extrair_corpo_sem_marcador("PAUTA", texto)

    match_dep = RE_DEPARTAMENTO_CT.search(corpo)
    departamento_origem = _normalizar_departamento(match_dep.group(1)) if match_dep else None

    match_decisao = RE_DECISAO_CT.search(corpo)
    if match_decisao:
        chave = match_decisao.group(1).upper()
        tipo_desfecho = _DESFECHO_CT.get(chave)
        resultado_votacao = match_decisao.group(2).strip() or None
        assunto = corpo[:match_decisao.start()].strip(" .")
    else:
        tipo_desfecho, resultado_votacao = None, None
        assunto = corpo.strip(" .")

    return CamposEnriquecidos(
        assunto=assunto or None, tipo_desfecho=tipo_desfecho, resultado_votacao=resultado_votacao,
        encaminhamento=None, ato_emitido=None, departamento_origem=departamento_origem,
    )


CONFIG_ENRIQUECEDOR[("B", "CT")] = extrair_ct
CONFIG_ENRIQUECEDOR[("A", "CEUNES")] = extrair_ct
CONFIG_ENRIQUECEDOR[("B", "CEUNES")] = extrair_ct


RE_PALAVRA_CHAVE_DESFECHO = re.compile(
    r"\b(APROVAD[OA]S?|REPROVAD[OA]S?|RETIRAD[OA]S?(?:\s+DE\s+PAUTA)?|ADIAD[OA]S?|"
    r"ENCAMINHAD[OA]S?|HOMOLOGAD[OA]S?)\b",
    re.IGNORECASE,
)

_DESFECHO_GENERICO = {
    "APROVADO": "Aprovado", "APROVADA": "Aprovado", "APROVADOS": "Aprovado", "APROVADAS": "Aprovado",
    "REPROVADO": "Reprovado", "REPROVADA": "Reprovado",
    "RETIRADO": "Retirado", "RETIRADA": "Retirado",
    "ADIADO": "Adiado", "ADIADA": "Adiado",
    "ENCAMINHADO": "Encaminhado", "ENCAMINHADA": "Encaminhado",
    "HOMOLOGADO": "Aprovado", "HOMOLOGADA": "Aprovado",
}


def extrair_generico(texto: str, data_reuniao: date | None) -> CamposEnriquecidos:
    corpo = extrair_corpo_sem_marcador("", texto)

    ocorrencias = list(RE_PALAVRA_CHAVE_DESFECHO.finditer(corpo))
    if not ocorrencias:
        return CamposEnriquecidos(
            assunto=corpo or None, tipo_desfecho=None, resultado_votacao=None,
            encaminhamento=None, ato_emitido=None, departamento_origem=None,
        )

    ultimo = ocorrencias[-1]
    palavra = re.sub(r"\s+DE\s+PAUTA$", "", ultimo.group(1).upper())
    chave = re.sub(r"S$", "", palavra)
    if chave not in _DESFECHO_GENERICO and palavra in _DESFECHO_GENERICO:
        chave = palavra
    tipo_desfecho = _DESFECHO_GENERICO.get(palavra) or _DESFECHO_GENERICO.get(chave)

    inicio_frase = corpo.rfind(".", 0, ultimo.start()) + 1
    resultado_votacao = corpo[inicio_frase:].strip(" .") or None
    assunto = corpo[:inicio_frase].strip(" .") or corpo[:ultimo.start()].strip(" .")

    return CamposEnriquecidos(
        assunto=assunto or None, tipo_desfecho=tipo_desfecho, resultado_votacao=resultado_votacao,
        encaminhamento=None, ato_emitido=None, departamento_origem=None,
    )


for _chave in [("B", "CAR"), ("B", "CEFD"), ("B", "CCAE"), ("B", "CE"), ("B", "CCHN"), ("B", "CCE"),
               ("A", "*"), ("C", "*"), ("D", "*")]:
    CONFIG_ENRIQUECEDOR[_chave] = extrair_generico


RE_ATO_EMITIDO = re.compile(
    r"Baixada a (DECIS[ÃA]O|RESOLU[ÇC][ÃA]O)\s+N[ÚU]MERO\s+([A-ZÀ-Ú ]+?)(?:,\s*DE|\s+BARRA)",
    re.IGNORECASE,
)

_TIPO_ATO = {"DECISAO": "DECISAO", "DECISÃO": "DECISAO", "RESOLUCAO": "RESOLUCAO", "RESOLUÇÃO": "RESOLUCAO"}


def _extrair_numero_extenso(bruto: str) -> int | None:
    tokens = tokenizar(bruto)
    valor, proximo = parse_cardinal(tokens, 0)
    if valor is None or proximo != len(tokens):
        return None
    return valor


def extrair_ccae(texto: str, data_reuniao: date) -> CamposEnriquecidos:
    campos_base = extrair_generico(texto, data_reuniao)

    match = RE_ATO_EMITIDO.search(texto)
    if not match:
        return campos_base

    tipo = _TIPO_ATO[remover_acentos_maiusculo(match.group(1))]
    numero = _extrair_numero_extenso(match.group(2).strip())
    ato_emitido = f"{tipo}_{numero}_{data_reuniao.year}" if numero is not None else None

    return CamposEnriquecidos(
        assunto=campos_base.assunto, tipo_desfecho=campos_base.tipo_desfecho,
        resultado_votacao=campos_base.resultado_votacao, encaminhamento=campos_base.encaminhamento,
        ato_emitido=ato_emitido, departamento_origem=None,
    )


CONFIG_ENRIQUECEDOR[("B", "CCAE")] = extrair_ccae


def main() -> None:
    engine = create_engine(settings.database_url)
    Sessao = sessionmaker(bind=engine)

    with Sessao() as sessao:
        documentos_com_itens = carregar_documentos_com_itens(sessao)
        total_itens = 0
        for documento, itens in documentos_com_itens:
            enriquecer_e_persistir(documento, itens, sessao)
            sessao.commit()
            total_itens += len(itens)
        print(f"{len(documentos_com_itens)} documentos processados, {total_itens} itens enriquecidos.")


if __name__ == "__main__":
    main()
