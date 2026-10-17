from __future__ import annotations

from collections import Counter

from neo4j import Driver
from qdrant_client import QdrantClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.grafo.cliente import executar_leitura, obter_driver
from app.ingestion.extractor import RE_GLIFO_TROCADO, RE_LIGADURA_UNICODE
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta

CONSULTAS_DO_GRAFO = {
    "atas": "MATCH (n:Ata) RETURN count(n) AS total",
    "deliberacoes": "MATCH (n:Deliberação) RETURN count(n) AS total",
    "encaminhamentos": "MATCH (n:Encaminhamento) RETURN count(n) AS total",
    "processos": "MATCH (n:Processo) RETURN count(n) AS total",
    "assuntos": "MATCH (n:Assunto) RETURN count(n) AS total",
    "mesmo_assunto": "MATCH ()-[r:trata_do_mesmo_assunto]->() RETURN count(r) AS total",
}


def _ligaduras_no_texto(texto: str) -> int:
    return len(RE_LIGADURA_UNICODE.findall(texto)) + len(RE_GLIFO_TROCADO.findall(texto)) + texto.count("Ɵ")


def totais_dos_itens(documentos: list[Documento], itens: list[ItemPauta]) -> dict:
    logicos = [i for i in itens if (i.fragmento_indice or 0) == 0]
    return {
        "atas": len(documentos),
        "atas_com_ocr": dict(Counter(d.orgao for d in documentos if d.paginas_ocr)),
        "itens_logicos": len(logicos),
        "linhas": len(itens),
        "desfechos": dict(Counter(i.tipo_desfecho for i in logicos)),
        "ato_emitido": sum(1 for i in logicos if i.ato_emitido),
        "departamento_origem": sum(1 for i in logicos if i.departamento_origem),
        "encaminhamento": sum(1 for i in logicos if i.encaminhamento),
        "ligaduras": sum(_ligaduras_no_texto(d.texto_limpo) for d in documentos),
    }


def totais_do_grafo(driver: Driver) -> dict:
    return {nome: executar_leitura(driver, consulta)[0]["total"] for nome, consulta in CONSULTAS_DO_GRAFO.items()}


def _numero(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def formatar_tabela(totais: dict) -> str:
    ocr = totais["atas_com_ocr"]
    por_orgao = ", ".join(f"{orgao} {n}" for orgao, n in sorted(ocr.items(), key=lambda par: -par[1]))
    desfechos = ", ".join(
        f"{desfecho or 'sem desfecho'} {_numero(n)}"
        for desfecho, n in sorted(totais["desfechos"].items(), key=lambda par: -par[1])
    )
    grafo = totais["grafo"]
    linhas = [
        "| | Valor |",
        "|---|---|",
        f"| Atas | {_numero(totais['atas'])} |",
        f"| Atas com páginas extraídas por OCR | {sum(ocr.values())} ({por_orgao}) |",
        f"| Itens de pauta lógicos / linhas com fragmentos | {_numero(totais['itens_logicos'])} / {_numero(totais['linhas'])} |",
        f"| Janelas no Qdrant | {_numero(totais['janelas'])} |",
        f"| Desfecho por item lógico | {desfechos} |",
        f"| Itens com ato emitido / departamento de origem / encaminhamento | "
        f"{totais['ato_emitido']} / {totais['departamento_origem']} / {totais['encaminhamento']} |",
        f"| Grafo | {_numero(grafo['atas'])} atas, {_numero(grafo['deliberacoes'])} deliberações, "
        f"{_numero(grafo['encaminhamentos'])} encaminhamentos, {_numero(grafo['processos'])} processos, "
        f"{_numero(grafo['assuntos'])} assuntos, {_numero(grafo['mesmo_assunto'])} relações `trata_do_mesmo_assunto` |",
        f"| Ligaduras ou glifos trocados no texto | {totais['ligaduras']} |",
    ]
    return "\n".join(linhas)


def main() -> None:
    engine = create_engine(settings.database_url)
    with sessionmaker(bind=engine)() as sessao:
        totais = totais_dos_itens(
            sessao.scalars(select(Documento)).all(), sessao.scalars(select(ItemPauta)).all()
        )

    cliente = QdrantClient(url=settings.qdrant_url)
    totais["janelas"] = cliente.count(settings.qdrant_collection, exact=True).count

    driver = obter_driver()
    try:
        totais["grafo"] = totais_do_grafo(driver)
    finally:
        driver.close()

    print(formatar_tabela(totais))


if __name__ == "__main__":
    main()
