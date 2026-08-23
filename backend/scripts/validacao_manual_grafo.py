from __future__ import annotations

import csv
import random
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.grafo.cliente import executar_leitura, obter_driver
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta

SEMENTE_AMOSTRAGEM = 42


def amostrar_itens(pares: list[tuple[Documento, ItemPauta]], n_por_variante: int) -> list[tuple[Documento, ItemPauta]]:
    por_variante: dict[tuple[str, str], list[tuple[Documento, ItemPauta]]] = {}
    for documento, item in pares:
        por_variante.setdefault((documento.tipo_orgao, documento.centro), []).append((documento, item))

    aleatorio = random.Random(SEMENTE_AMOSTRAGEM)
    amostra = []
    for grupo in por_variante.values():
        amostra.extend(aleatorio.sample(grupo, min(n_por_variante, len(grupo))))
    return amostra


def gerar_linha_csv(documento: Documento, item: ItemPauta, relacoes_assunto: list[str], processos: list[str]) -> dict:
    return {
        "item_id_canonico": item.item_id_canonico,
        "ata": documento.nome_arquivo,
        "pagina": item.pagina_inicio,
        "trecho": item.texto[:300],
        "assunto": item.assunto,
        "departamento_origem": item.departamento_origem,
        "tipo_desfecho": item.tipo_desfecho,
        "resultado_votacao": item.resultado_votacao,
        "encaminhamento": item.encaminhamento,
        "ato_emitido": item.ato_emitido,
        "processos_mencionados": "; ".join(processos),
        "outros_itens_mesmo_assunto": "; ".join(relacoes_assunto),
        "correto": "",
        "categoria_erro": "",
        "observacao": "",
    }


def exportar_csv(caminho: Path, linhas: list[dict]) -> None:
    with open(caminho, "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(linhas[0].keys()))
        escritor.writeheader()
        escritor.writerows(linhas)


def main() -> None:
    engine = create_engine(settings.database_url)
    Sessao = sessionmaker(bind=engine)
    driver = obter_driver()

    try:
        with Sessao() as sessao:
            pares = [
                (documento, item)
                for documento in sessao.execute(select(Documento)).scalars().all()
                for item in sessao.execute(
                    select(ItemPauta).where(ItemPauta.documento_id == documento.id_documento)
                ).scalars().all()
            ]
            amostra = amostrar_itens(pares, n_por_variante=5)

            linhas = []
            for documento, item in amostra:
                processos = executar_leitura(
                    driver,
                    "MATCH (:ItemPauta {item_id_canonico: $id})-[:MENCIONA]->(p:Processo) RETURN p.token AS token",
                    id=item.item_id_canonico,
                )
                relacoes_assunto = executar_leitura(
                    driver,
                    "MATCH (:ItemPauta {item_id_canonico: $id})-[:TRATA_DE]->(:Assunto)<-[:TRATA_DE]-(outro:ItemPauta) "
                    "RETURN outro.item_id_canonico AS id",
                    id=item.item_id_canonico,
                )
                linhas.append(gerar_linha_csv(
                    documento, item,
                    [r["id"] for r in relacoes_assunto],
                    [p["token"] for p in processos],
                ))

            exportar_csv(Path("validacao_manual_grafo.csv"), linhas)
            print(f"{len(linhas)} itens amostrados para validacao manual.")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
