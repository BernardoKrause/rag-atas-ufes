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
    RE_ENCERRAMENTO_ATA, RE_ITEM_CAR, RE_ITEM_CCE, RE_ITEM_CE_D, RE_ITEM_CEFD, RE_ITEM_CT,
    RE_ITEM_PONTILHADO, SECAO_COMUNICACOES, SECAO_EXPEDIENTE, SECAO_INFORMES, SECAO_PALAVRA_LIVRE,
    SOBREPOSICAO_FRAGMENTO,
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

    return re.sub(r"^[\s–—-]+", "", texto).strip()


ExtratorEnriquecimento = Callable[[str, date, str | None], CamposEnriquecidos]

CONFIG_ENRIQUECEDOR: dict[tuple[str, str], ExtratorEnriquecimento] = {}


def _obter_extrator(tipo_orgao: str, centro: str) -> ExtratorEnriquecimento:
    if (tipo_orgao, centro) in CONFIG_ENRIQUECEDOR:
        return CONFIG_ENRIQUECEDOR[(tipo_orgao, centro)]
    if (tipo_orgao, "*") in CONFIG_ENRIQUECEDOR:
        return CONFIG_ENRIQUECEDOR[(tipo_orgao, "*")]
    raise ValueError(f"variante sem extrator mapeado: tipo_orgao={tipo_orgao!r} centro={centro!r}")


def enriquecer_item(
    tipo_orgao: str, centro: str, item_texto: str, data_reuniao: date, secao: str | None = None,
) -> CamposEnriquecidos:
    extrator = _obter_extrator(tipo_orgao, centro)
    return extrator(item_texto, data_reuniao, secao=secao)


def reconstruir_texto_do_item(fragmentos: list[str]) -> str:
    return fragmentos[0] + "".join(f[SOBREPOSICAO_FRAGMENTO:] for f in fragmentos[1:])


def enriquecer_e_persistir(documento: Documento, itens: list[ItemPauta], sessao: Session) -> None:
    por_item: dict[tuple[str, str, int], list[ItemPauta]] = {}
    for item in itens:
        por_item.setdefault((item.secao, item.numero_item, item.ocorrencia_indice), []).append(item)
    for fragmentos in por_item.values():
        fragmentos.sort(key=lambda f: f.fragmento_indice)
        texto = reconstruir_texto_do_item([f.texto for f in fragmentos])
        campos = enriquecer_item(
            documento.tipo_orgao, documento.centro, texto, documento.data_reuniao, secao=fragmentos[0].secao,
        )
        for fragmento in fragmentos:
            fragmento.assunto = campos.assunto
            fragmento.tipo_desfecho = campos.tipo_desfecho
            fragmento.resultado_votacao = campos.resultado_votacao
            fragmento.encaminhamento = campos.encaminhamento
            fragmento.ato_emitido = campos.ato_emitido
            fragmento.departamento_origem = campos.departamento_origem
    sessao.flush()


_ABREVIACOES = {"dr", "dra", "drª", "prof", "profa", "profª", "sr", "sra", "nº", "n", "art", "cons", "depart", "doc", "prot"}

RE_PONTO_FINAL_DE_FRASE = re.compile(r"\.[”\"’'»)\]]*(?=\s|$)")
RE_ULTIMA_PALAVRA = re.compile(r"([\wª]+)$")
_JANELA_ABREVIACAO = 20


def _pontos_de_fronteira(texto: str) -> list[int]:
    fronteiras = []
    for match in RE_PONTO_FINAL_DE_FRASE.finditer(texto):
        palavra = RE_ULTIMA_PALAVRA.search(texto, max(0, match.start() - _JANELA_ABREVIACAO), match.start())
        if palavra and palavra.group(1).lower() in _ABREVIACOES:
            continue
        fronteiras.append(match.end())
    return fronteiras


def _limites_da_frase(texto: str, posicao: int) -> tuple[int, int]:
    inicio, fim = 0, len(texto)
    for fronteira in _pontos_de_fronteira(texto):
        if fronteira <= posicao:
            inicio = fronteira
        else:
            fim = fronteira
            break
    return inicio, fim


RE_ENCAMINHAMENTO_DOIS_PONTOS = re.compile(r"\bencaminhamento\b[^.:,\n]{0,80}:(?!\d)\s*", re.IGNORECASE)
RE_ENCAMINHAMENTO_DESTINO = re.compile(r"\bencaminhamento\s+(?:[àa]s?|ao|aos|para)\s+(?!(?:a\s+)?vota)", re.IGNORECASE)


def extrair_encaminhamento(corpo: str) -> str | None:
    for padrao in (RE_ENCAMINHAMENTO_DOIS_PONTOS, RE_ENCAMINHAMENTO_DESTINO):
        match = padrao.search(corpo)
        if not match:
            continue
        fim = _limites_da_frase(corpo, match.end())[1]
        inicio = match.end() if padrao is RE_ENCAMINHAMENTO_DOIS_PONTOS else match.start()
        return corpo[inicio:fim].strip(" .") or None
    return None


_ROTULO_DECISAO_CT = r"Decis[ãa]o\s*[:;]\s*(?:(?:[^\w\s]|\w{1,2}(?=\s))\s*){0,3}?"
RE_DECISAO_CT = re.compile(_ROTULO_DECISAO_CT + r"([A-ZÀ-Ú][a-zà-ú]+)\(?a?\)?\.?\s*(.*)", re.DOTALL)
RE_DECISAO_NAO_APROVADO_CT = re.compile(_ROTULO_DECISAO_CT + r"N[ãa]o\s+aprovad[oa]\(?a?\)?\.?\s*(.*)", re.DOTALL)
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


def extrair_ct(texto: str, data_reuniao: date, secao: str | None = None) -> CamposEnriquecidos:
    corpo = extrair_corpo_sem_marcador("PAUTA", texto)

    match_dep = RE_DEPARTAMENTO_CT.search(corpo)
    departamento_origem = _normalizar_departamento(match_dep.group(1)) if match_dep else None

    match_nao_aprovado = RE_DECISAO_NAO_APROVADO_CT.search(corpo)
    match_decisao = RE_DECISAO_CT.search(corpo)
    if match_nao_aprovado:
        tipo_desfecho = "Reprovado"
        resultado = match_nao_aprovado.group(1).strip()
        resultado_votacao = resultado[:_limites_da_frase(resultado, 0)[1]].strip() or None
        assunto = corpo[:match_nao_aprovado.start()].strip(" .")
    elif match_decisao:
        chave = match_decisao.group(1).upper()
        tipo_desfecho = _DESFECHO_CT.get(chave)
        resultado = match_decisao.group(2).strip()
        resultado_votacao = resultado[:_limites_da_frase(resultado, 0)[1]].strip() or None
        assunto = corpo[:match_decisao.start()].strip(" .")
    else:
        tipo_desfecho, resultado_votacao = None, None
        assunto = corpo.strip(" .")

    encaminhamento = extrair_encaminhamento(corpo) if tipo_desfecho else None

    return CamposEnriquecidos(
        assunto=assunto or None, tipo_desfecho=tipo_desfecho, resultado_votacao=resultado_votacao,
        encaminhamento=encaminhamento, ato_emitido=None, departamento_origem=departamento_origem,
    )


CONFIG_ENRIQUECEDOR[("B", "CT")] = extrair_ct
CONFIG_ENRIQUECEDOR[("A", "CEUNES")] = extrair_ct
CONFIG_ENRIQUECEDOR[("B", "CEUNES")] = extrair_ct


RE_PALAVRA_CHAVE_DESFECHO = re.compile(
    r"\b(N[ÃA]O\s+(?:FOI\s+|FORAM\s+)?APROVAD[OA]S?|REJEITAD[OA]S?|INDEFERID[OA]S?|APROVAD[OA]S?|REPROVAD[OA]S?|RETIRAD[OA]S?(?:\s+DE\s+PAUTA)?|BAIXAD[OA]S?\s+DE\s+PAUTA|ADIAD[OA]S?|"
    r"ENCAMINHAD[OA]S?|HOMOLOGAD[OA]S?)\b",
    re.IGNORECASE,
)

_DESFECHO_GENERICO = {
    "APROVADO": "Aprovado", "APROVADA": "Aprovado", "APROVADOS": "Aprovado", "APROVADAS": "Aprovado",
    "REPROVADO": "Reprovado", "REPROVADA": "Reprovado",
    "RETIRADO": "Retirado", "RETIRADA": "Retirado",
    "BAIXADO": "Retirado", "BAIXADA": "Retirado",
    "ADIADO": "Adiado", "ADIADA": "Adiado",
    "ENCAMINHADO": "Encaminhado", "ENCAMINHADA": "Encaminhado",
    "HOMOLOGADO": "Aprovado", "HOMOLOGADA": "Aprovado",
    "REJEITADO": "Reprovado", "REJEITADA": "Reprovado", "INDEFERIDO": "Reprovado", "INDEFERIDA": "Reprovado",
}
RE_REJEICAO = re.compile(r"N[ÃA]O\s+|REJEITAD|INDEFERID", re.IGNORECASE)


RE_MARCA_DE_VOTACAO = re.compile(r"votaç|votac|unanimidade|maioria|\bvotos?\b|abstenç|contrári", re.IGNORECASE)
RE_RETIRADO = re.compile(r"RETIRAD[OA]S?(?:\s+DE\s+PAUTA)?$", re.IGNORECASE)
RE_BAIXADO = re.compile(r"BAIXAD", re.IGNORECASE)
RE_APROVADO = re.compile(r"APROVAD[OA]S?$", re.IGNORECASE)
RE_MARCA_DE_APROVACAO_DELIBERATIVA = re.compile(
    r"aprovad[oa]s?\s+(?:\S+\s+){0,3}pel[oa]s?\s+(presentes|membros|conselheir|conselho|c[aâ]mara|colegiado)"
    r"|discutid[oa]s?\s+e\s+aprovad|sendo\s+aprovad|ap[oó]s\s+(ampla\s+)?(discuss|apreci|esclarec)",
    re.IGNORECASE,
)
RE_NEGACAO_DE_APROVACAO = re.compile(r"n[aã]o\s+(foi\s+|ser[aã]o?\s+|mais\s+)*aprovad", re.IGNORECASE)
RE_ATA_LIDA_E_APROVADA = re.compile(r"lida\s+e\s+aprovada", re.IGNORECASE)
_SECOES_NAO_DELIBERATIVAS = {SECAO_INFORMES, SECAO_COMUNICACOES, SECAO_EXPEDIENTE, SECAO_PALAVRA_LIVRE}


def _secao_deliberativa(secao: str | None) -> bool:
    return secao is not None and secao not in _SECOES_NAO_DELIBERATIVAS


def _ocorrencia_valida(corpo: str, ocorrencia: re.Match) -> bool:
    inicio, fim = _limites_da_frase(corpo, ocorrencia.start())
    frase = corpo[inicio:fim]
    if RE_REJEICAO.match(ocorrencia.group(1)):
        antes = corpo[inicio:ocorrencia.start()].rstrip().lower()
        return bool(RE_MARCA_DE_VOTACAO.search(frase)) and not antes.endswith(" ou")
    if RE_MARCA_DE_VOTACAO.search(frase) and not RE_NEGACAO_DE_APROVACAO.search(frase):
        return True
    if RE_PALAVRA_CHAVE_DESFECHO.match(frase.lstrip()):
        return True
    palavra = ocorrencia.group(1)
    if RE_REJEICAO.match(palavra):
        return False
    if re.search(r"\s+DE\s+PAUTA$", palavra, re.IGNORECASE):
        return True
    if RE_RETIRADO.match(palavra):
        depois = corpo[ocorrencia.end():fim].strip(" .")
        antes = corpo[inicio:ocorrencia.start()].rstrip()
        return not depois or antes.lower().endswith("pauta")
    return False


def _aprovacao_deliberativa_valida(corpo: str, ocorrencia: re.Match) -> bool:
    if not RE_APROVADO.match(ocorrencia.group(1)):
        return False
    inicio, fim = _limites_da_frase(corpo, ocorrencia.start())
    frase = corpo[inicio:fim]
    return (
        bool(RE_MARCA_DE_APROVACAO_DELIBERATIVA.search(frase))
        and not RE_NEGACAO_DE_APROVACAO.search(frase)
        and not RE_ATA_LIDA_E_APROVADA.search(frase)
    )


RE_APROVACAO_ATA_INVERTIDA = re.compile(
    r"^Foi\s+apreciad[oa]\s+e\s+aprovad[oa],?\s+por\s+unanimidade\s*:\s*", re.IGNORECASE
)


def extrair_generico(texto: str, data_reuniao: date | None, secao: str | None = None) -> CamposEnriquecidos:
    match_invertido = RE_APROVACAO_ATA_INVERTIDA.match(texto)
    if match_invertido:
        resultado_votacao = match_invertido.group(0).strip(" :")
        assunto = extrair_corpo_sem_marcador("", texto[match_invertido.end():]).strip(" .")
        return CamposEnriquecidos(
            assunto=assunto or None, tipo_desfecho="Aprovado", resultado_votacao=resultado_votacao,
            encaminhamento=None, ato_emitido=None, departamento_origem=None,
        )

    corpo = extrair_corpo_sem_marcador("", texto)

    candidatas = [
        o for o in RE_PALAVRA_CHAVE_DESFECHO.finditer(corpo)
        if _secao_deliberativa(secao) or not RE_BAIXADO.match(o.group(1))
    ]
    ocorrencias = [o for o in candidatas if _ocorrencia_valida(corpo, o)]
    if not ocorrencias and _secao_deliberativa(secao):
        ocorrencias = [o for o in candidatas if _aprovacao_deliberativa_valida(corpo, o)]
    if not ocorrencias:
        return CamposEnriquecidos(
            assunto=corpo or None, tipo_desfecho=None, resultado_votacao=None,
            encaminhamento=None, ato_emitido=None, departamento_origem=None,
        )

    ultimo = ocorrencias[-1]
    palavra = re.sub(r"\s+DE\s+PAUTA$", "", ultimo.group(1).upper())
    if re.match(r"N[ÃA]O\s", palavra):
        tipo_desfecho = "Reprovado"
    else:
        chave = re.sub(r"S$", "", palavra)
        if chave not in _DESFECHO_GENERICO and palavra in _DESFECHO_GENERICO:
            chave = palavra
        tipo_desfecho = _DESFECHO_GENERICO.get(palavra) or _DESFECHO_GENERICO.get(chave)

    inicio_frase, fim_frase = _limites_da_frase(corpo, ultimo.start())
    resultado_votacao = corpo[inicio_frase:fim_frase].strip(" .") or None
    assunto = corpo[:inicio_frase].strip(" .") or corpo[:ultimo.start()].strip(" .")
    encaminhamento = extrair_encaminhamento(corpo) if tipo_desfecho else None

    return CamposEnriquecidos(
        assunto=assunto or None, tipo_desfecho=tipo_desfecho, resultado_votacao=resultado_votacao,
        encaminhamento=encaminhamento, ato_emitido=None, departamento_origem=None,
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


def extrair_ccae(texto: str, data_reuniao: date, secao: str | None = None) -> CamposEnriquecidos:
    campos_base = extrair_generico(texto, data_reuniao, secao)

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
