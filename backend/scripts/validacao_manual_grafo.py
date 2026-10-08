from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.grafo.cliente import executar_leitura, obter_driver
from app.models.consultas import carregar_documentos_com_itens
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta

SEMENTE_AMOSTRAGEM = 42
LIMITE_ESTRATO_SUPLEMENTAR = 8
DESFECHOS_RAROS = ("Reprovado", "Adiado")
N_POR_TIPO = 15


def _sortear(
    candidatos: list[tuple[Documento, ItemPauta]],
    limite: int | None,
    ja_escolhidos: set[str],
    aleatorio: random.Random,
) -> list[tuple[Documento, ItemPauta]]:
    disponiveis = [p for p in candidatos if p[1].item_id_canonico not in ja_escolhidos]
    if limite is None:
        escolhidos = disponiveis
    else:
        escolhidos = aleatorio.sample(disponiveis, min(limite, len(disponiveis)))
    ja_escolhidos.update(p[1].item_id_canonico for p in escolhidos)
    return escolhidos


def _sortear_por_tipo(
    pares: list[tuple[Documento, ItemPauta]],
    n_por_tipo: int,
    ja_escolhidos: set[str],
    aleatorio: random.Random,
) -> list[tuple[Documento, ItemPauta]]:
    por_tipo: dict[str, dict[str, list[tuple[Documento, ItemPauta]]]] = {}
    for documento, item in pares:
        por_tipo.setdefault(documento.tipo_orgao, {}).setdefault(documento.centro, []).append((documento, item))

    amostra = []
    for tipo in sorted(por_tipo):
        filas = [aleatorio.sample(grupo, len(grupo)) for _, grupo in sorted(por_tipo[tipo].items())]
        escolhidos: list[tuple[Documento, ItemPauta]] = []
        while len(escolhidos) < n_por_tipo and any(filas):
            for fila in filas:
                if fila and len(escolhidos) < n_por_tipo:
                    par = fila.pop()
                    if par[1].item_id_canonico not in ja_escolhidos:
                        ja_escolhidos.add(par[1].item_id_canonico)
                        escolhidos.append(par)
        amostra.extend(escolhidos)
    return amostra


def amostrar_itens(pares: list[tuple[Documento, ItemPauta]], n_por_tipo: int) -> list[tuple[Documento, ItemPauta]]:
    # TCC1: tipos A-D em proporcao equivalente; estratos suplementares porque
    # campos raros (ato_emitido, departamento_origem) quase nunca caem na amostra base
    aleatorio = random.Random(SEMENTE_AMOSTRAGEM)
    ja_escolhidos: set[str] = set()
    amostra = _sortear_por_tipo(pares, n_por_tipo, ja_escolhidos, aleatorio)

    suplementares: list[tuple[list[tuple[Documento, ItemPauta]], int | None]] = [
        ([p for p in pares if p[1].ato_emitido], LIMITE_ESTRATO_SUPLEMENTAR),
        ([p for p in pares if p[1].departamento_origem], LIMITE_ESTRATO_SUPLEMENTAR),
        ([p for p in pares if p[1].tipo_desfecho in DESFECHOS_RAROS], None),
    ]
    for candidatos, limite in suplementares:
        amostra.extend(_sortear(candidatos, limite, ja_escolhidos, aleatorio))

    return amostra


def filtrar_por_ids(pares: list[tuple[Documento, ItemPauta]], ids: set[str]) -> list[tuple[Documento, ItemPauta]]:
    return [p for p in pares if p[1].item_id_canonico in ids]


def _item_veio_de_ocr(documento: Documento, item: ItemPauta) -> bool:
    if not documento.paginas_ocr or item.pagina_inicio is None:
        return False
    fim = item.pagina_fim if item.pagina_fim is not None else item.pagina_inicio
    return any(item.pagina_inicio <= pagina <= fim for pagina in documento.paginas_ocr)


def gerar_linha_csv(documento: Documento, item: ItemPauta, relacoes_assunto: list[str], processos: list[str]) -> dict:
    return {
        "item_id_canonico": item.item_id_canonico,
        "ata": documento.nome_arquivo,
        "tipo_orgao": documento.tipo_orgao,
        "centro": documento.centro,
        "orgao": documento.orgao,
        "pagina": item.pagina_inicio,
        "ocr": "sim" if _item_veio_de_ocr(documento, item) else "nao",
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
    if not linhas:
        print("nenhum item correspondente; nada foi gravado.")
        return
    with open(caminho, "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(linhas[0].keys()))
        escritor.writeheader()
        escritor.writerows(linhas)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", type=Path, help="arquivo com um item_id_canonico por linha (revalidacao)")
    args = parser.parse_args()

    engine = create_engine(settings.database_url)
    Sessao = sessionmaker(bind=engine)
    driver = obter_driver()

    try:
        with Sessao() as sessao:
            pares = [
                (documento, item)
                for documento, itens in carregar_documentos_com_itens(sessao)
                for item in itens
            ]
            if args.ids:
                ids = {linha.strip() for linha in args.ids.read_text(encoding="utf-8").splitlines() if linha.strip()}
                amostra = filtrar_por_ids(pares, ids)
                destino = Path("validacao_revalidacao.csv")
            else:
                amostra = amostrar_itens(pares, n_por_tipo=N_POR_TIPO)
                destino = Path("validacao_manual_grafo.csv")

            linhas = []
            for documento, item in amostra:
                processos = executar_leitura(
                    driver,
                    "MATCH (:ItemPauta {item_id_canonico: $id})-[:MENCIONA]->(p:Processo) "
                    "RETURN p.token AS token ORDER BY token",
                    id=item.item_id_canonico,
                )
                relacoes_assunto = executar_leitura(
                    driver,
                    "MATCH (:ItemPauta {item_id_canonico: $id})-[:TRATA_DE]->(:Assunto)<-[:TRATA_DE]-(outro:ItemPauta) "
                    "RETURN outro.item_id_canonico AS id ORDER BY id",
                    id=item.item_id_canonico,
                )
                linhas.append(gerar_linha_csv(
                    documento, item,
                    [r["id"] for r in relacoes_assunto],
                    [p["token"] for p in processos],
                ))

            exportar_csv(destino, linhas)
            if linhas:
                print(f"{len(linhas)} itens exportados para {destino}.")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
