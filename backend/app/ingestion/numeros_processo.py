from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.ingestion.cleaner import (
    RE_NUMERO_PROCESSO,
    TipoEntidade,
    _gerar_hash_entidade,
    _normalizar_entidade,
)
from app.ingestion.collector import path_seguro
from app.ingestion.extractor import extrair_texto_bruto, verificar_tesseract
from app.models.documento import Documento, EntidadeAnonimizada, NumeroProcesso


def registrar_numeros(texto_bruto: str, secret_key: bytes, sessao: Session) -> tuple[int, int]:
    encontrados, sem_token = 0, 0
    for match in RE_NUMERO_PROCESSO.finditer(texto_bruto):
        hash_entidade = _gerar_hash_entidade(secret_key, TipoEntidade.PROCESSO, match.group())
        token = sessao.scalar(
            select(EntidadeAnonimizada.token).where(EntidadeAnonimizada.hash_entidade == hash_entidade)
        )
        if token is None:
            sem_token += 1
            continue
        numero = _normalizar_entidade(TipoEntidade.PROCESSO, match.group())
        sessao.merge(NumeroProcesso(token=token, numero=numero))
        encontrados += 1
    sessao.flush()
    return encontrados, sem_token


def main() -> None:
    verificar_tesseract()
    secret_key = settings.anonymization_secret_key.get_secret_value().encode()
    Sessao = sessionmaker(bind=create_engine(settings.database_url))
    encontrados, sem_token, sem_pdf = 0, 0, []
    with Sessao() as sessao:
        documentos = sessao.execute(
            select(Documento.id_documento, Documento.url_origem).order_by(Documento.id_documento)
        ).all()
        for id_documento, url_origem in documentos:
            caminho = path_seguro(Path(url_origem))
            if not caminho.is_file():
                sem_pdf.append(id_documento)
                continue
            texto_bruto, _, _ = extrair_texto_bruto(caminho)
            achados, faltando = registrar_numeros(texto_bruto, secret_key, sessao)
            encontrados += achados
            sem_token += faltando
            sessao.commit()
            print(f"ata {id_documento}: {achados} encontrados, {faltando} sem token", flush=True)
    print(f"total: {encontrados} ocorrências, {sem_token} sem token, atas sem PDF: {sem_pdf}")


if __name__ == "__main__":
    main()
