from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.ingestion.cleaner import anonimizar_texto, remapear_offsets
from app.ingestion.collector import PREFIXO_PATH_ESTENDIDO, AtaParaProcessar, coletar_atas
from app.ingestion.extractor import extrair_campos
from app.models.documento import Documento, StatusAprovacao


def _url_origem(caminho_pdf: Path) -> str:
    texto = str(caminho_pdf)
    if texto.startswith(PREFIXO_PATH_ESTENDIDO):
        return texto[len(PREFIXO_PATH_ESTENDIDO) :]
    return texto


def processar_ata(ata: AtaParaProcessar, secret_key: bytes, sessao: Session) -> Documento:
    """Extrai, anonimiza e persiste uma ata como Documento.

    Idempotente por (tipo_orgao, orgao, nome_arquivo): reprocessar a mesma ata
    atualiza o registro existente em vez de duplicar — necessario pra Parte 10
    reprocessar o corpus inteiro sobre este mesmo pipeline sem gerar
    duplicatas. nome_arquivo sozinho nao basta: orgaos diferentes podem
    nomear atas com o mesmo padrao generico (ex.: "10-2025.pdf").
    """
    campos = extrair_campos(ata.tipo, ata.orgao, ata.caminho_pdf)
    texto_limpo, substituicoes = anonimizar_texto(campos["texto_bruto"], secret_key, sessao)

    documento = sessao.execute(
        select(Documento).filter_by(
            tipo_orgao=campos["tipo_orgao"], orgao=ata.orgao, nome_arquivo=ata.arquivo
        )
    ).scalar_one_or_none()
    if documento is None:
        documento = Documento(orgao=ata.orgao, nome_arquivo=ata.arquivo)
        sessao.add(documento)

    documento.url_origem = _url_origem(ata.caminho_pdf)
    documento.centro = campos["centro"]
    documento.campus = campos["campus"]
    documento.tipo_orgao = campos["tipo_orgao"]
    documento.departamento = campos["departamento"]
    documento.curso = campos["curso"]
    documento.area_tematica = campos["area_tematica"]
    documento.numero_reuniao = ata.numero_reuniao
    documento.tipo_reuniao = ata.caratere or None
    documento.data_reuniao = ata.data_reuniao
    documento.horario_inicio = campos["horario_inicio"]
    documento.modalidade = campos["modalidade"]
    documento.local = campos["local"]
    documento.quorum_declarado = campos["quorum_declarado"]
    documento.status_aprovacao = (
        StatusAprovacao.PENDENTE_APROVACAO.value
        if campos["em_aprovacao"]
        else StatusAprovacao.APROVADA.value
    )
    documento.texto_limpo = texto_limpo
    # paginas_offsets vem do extrator sobre texto_bruto (pre-anonimizacao);
    # remapeado aqui pro espaco de texto_limpo, que e o que fica persistido
    # e o que segmentador.py usa pra calcular pagina_inicio/pagina_fim
    documento.paginas_offsets = remapear_offsets(campos["paginas_offsets"], substituicoes)

    sessao.flush()
    return documento


def executar_pipeline(
    atas_corpus_path: Path, secret_key: bytes, sessao: Session
) -> list[Documento]:
    """Commita apos cada ata processada: uma ata que falha (PDF corrompido,
    orgao desconhecido) aborta o restante do corpus, mas as atas ja
    processadas com sucesso nesta execucao permanecem persistidas em vez de
    serem descartadas — um rerun, sendo idempotente, so reprocessa o que
    faltou."""
    atas = coletar_atas(atas_corpus_path)
    documentos = []
    for ata in atas:
        documentos.append(processar_ata(ata, secret_key, sessao))
        sessao.commit()
    return documentos


def main() -> None:
    engine = create_engine(settings.database_url)
    Sessao = sessionmaker(bind=engine)

    with Sessao() as sessao:
        documentos = executar_pipeline(
            settings.atas_corpus_path,
            settings.anonymization_secret_key.get_secret_value().encode(),
            sessao,
        )
        print(f"{len(documentos)} atas processadas.")


if __name__ == "__main__":
    main()
