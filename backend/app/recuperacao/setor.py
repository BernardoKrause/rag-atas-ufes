from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.documento import Documento

RE_SETOR = re.compile(r"\bno setor\s+(\w+(?:\s*/\s*\w+)*)", re.IGNORECASE)

NOMES_POR_EXTENSO = {
    "CAR": "Centro de Artes",
    "CCAE": "Centro de Ciências Agrárias e Engenharias",
    "CCE": "Centro de Ciências Exatas",
    "CCHN": "Centro de Ciências Humanas e Naturais",
    "CE": "Centro de Educação",
    "CEFD": "Centro de Educação Física e Desportos",
    "CEUNES": "Centro Universitário Norte do Espírito Santo",
    "CT": "Centro Tecnológico",
    "CCAE_DEAL": "Departamento de Engenharia de Alimentos",
    "CCAE_DER": "Departamento de Engenharia Rural",
    "CCAE_DPV": "Departamento de Produção Vegetal",
    "CCENS_DB": "Departamento de Biologia",
    "CCENS_DC": "Departamento de Computação",
    "CCENS_DFN": "Departamento de Farmácia e Nutrição",
    "CCENS_DG": "Departamento de Geologia",
    "CCENS_DMPA": "Departamento de Matemática Pura e Aplicada",
    "CCENS_DQF": "Departamento de Química e Física",
    "CEUNES_DCE": "Departamento de Computação e Eletrônica",
    "CEUNES_DCN": "Departamento de Ciências Naturais",
    "CEUNES_DCS": "Departamento de Ciências da Saúde",
    "CEUNES_DET": "Departamento de Engenharia e Tecnologia",
    "CEUNES_DMA": "Departamento de Matemática Aplicada",
    "CCHN_CamaraLocal_Graduacao": "Câmara Local de Graduação do Centro de Ciências Humanas e Naturais",
    "CE_Colegiado_Pedagogia": "Colegiado do Curso de Pedagogia",
}


def identificar_orgao(pergunta: str, sessao: Session) -> str | None:
    match = RE_SETOR.search(pergunta)
    if not match:
        return None
    chave = "_".join(re.split(r"\s*/\s*", match.group(1))).upper()
    orgaos = sessao.execute(select(Documento.orgao).distinct()).scalars()
    return next((orgao for orgao in orgaos if orgao.upper() == chave), None)


def documentos_do_orgao(orgao: str, sessao: Session) -> list[int]:
    return list(sessao.execute(select(Documento.id_documento).where(Documento.orgao == orgao)).scalars())


def listar_orgaos(sessao: Session) -> list[tuple[str, int]]:
    linhas = sessao.execute(
        select(Documento.orgao, func.count()).group_by(Documento.orgao).order_by(Documento.orgao)
    )
    return [(orgao, total) for orgao, total in linhas]
