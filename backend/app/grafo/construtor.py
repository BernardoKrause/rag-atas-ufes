from __future__ import annotations

import hashlib
import re
import unicodedata

from neo4j import Driver

from app.grafo.cliente import executar_escrita
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta


RE_TOKEN_PROCESSO = re.compile(r"PROCESSO_\d{4,}")


def limpar_grafo(driver: Driver) -> None:
    executar_escrita(driver, "MATCH (n) DETACH DELETE n")


def criar_no_ata(driver: Driver, documento: Documento) -> None:
    executar_escrita(
        driver,
        """
        MERGE (a:Ata {documento_id: $documento_id})
        SET a.nome_arquivo = $nome_arquivo, a.tipo_orgao = $tipo_orgao
        MERGE (c:Centro {sigla: $centro})
        MERGE (a)-[:PERTENCE_A]->(c)
        MERGE (d:Data {valor: $data_reuniao})
        MERGE (a)-[:POSSUI]->(d)
        """,
        documento_id=documento.id_documento, nome_arquivo=documento.nome_arquivo,
        tipo_orgao=documento.tipo_orgao, centro=documento.centro,
        data_reuniao=documento.data_reuniao.isoformat(),
    )
    if documento.departamento:
        executar_escrita(
            driver,
            "MATCH (a:Ata {documento_id: $documento_id}) "
            "MERGE (dep:Departamento {sigla: $departamento}) "
            "MERGE (a)-[:PERTENCE_A]->(dep)",
            documento_id=documento.id_documento, departamento=documento.departamento,
        )


def criar_no_item(driver: Driver, documento_id: int, item: ItemPauta) -> None:
    executar_escrita(
        driver,
        """
        MATCH (a:Ata {documento_id: $documento_id})
        MERGE (i:ItemPauta {item_id_canonico: $item_id})
        SET i.secao = $secao, i.numero_item = $numero_item,
            i.pagina_inicio = $pagina_inicio, i.pagina_fim = $pagina_fim,
            i.trecho = $trecho
        MERGE (a)-[:CONTEM]->(i)
        """,
        documento_id=documento_id, item_id=item.item_id_canonico, secao=item.secao,
        numero_item=item.numero_item, pagina_inicio=item.pagina_inicio, pagina_fim=item.pagina_fim,
        trecho=item.texto[:500],
    )
    for token in set(RE_TOKEN_PROCESSO.findall(item.texto)):
        executar_escrita(
            driver,
            "MATCH (i:ItemPauta {item_id_canonico: $item_id}) "
            "MERGE (p:Processo {token: $token}) "
            "MERGE (i)-[:MENCIONA {pagina: $pagina, trecho: $trecho}]->(p)",
            item_id=item.item_id_canonico, token=token,
            pagina=item.pagina_inicio, trecho=item.texto[:500],
        )


class UnionFind:
    def __init__(self) -> None:
        self._pai: dict[str, str] = {}

    def find(self, x: str) -> str:
        self._pai.setdefault(x, x)
        if self._pai[x] != x:
            self._pai[x] = self.find(self._pai[x])
        return self._pai[x]

    def union(self, x: str, y: str) -> None:
        raiz_x, raiz_y = self.find(x), self.find(y)
        if raiz_x != raiz_y:
            self._pai[raiz_x] = raiz_y


def _normalizar_assunto(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", sem_acento.upper())).strip()


def agrupar_assuntos(itens: list[ItemPauta]) -> dict[str, list[ItemPauta]]:
    """Componentes conectados: dois itens caem no mesmo Assunto se
    compartilham um token de Processo (sinal forte) ou tem assunto
    normalizado identico (sinal fraco, risco de falso-positivo medido na
    validacao manual — ver Task 15)."""
    uniao = UnionFind()
    for item in itens:
        uniao.find(item.item_id_canonico)

    por_processo: dict[str, list[ItemPauta]] = {}
    por_assunto: dict[str, list[ItemPauta]] = {}
    for item in itens:
        for token in set(RE_TOKEN_PROCESSO.findall(item.texto)):
            por_processo.setdefault(token, []).append(item)
        if item.assunto:
            chave = _normalizar_assunto(item.assunto)
            if chave:
                por_assunto.setdefault(chave, []).append(item)

    for grupo in list(por_processo.values()) + list(por_assunto.values()):
        for outro in grupo[1:]:
            uniao.union(grupo[0].item_id_canonico, outro.item_id_canonico)

    componentes: dict[str, list[ItemPauta]] = {}
    for item in itens:
        raiz = uniao.find(item.item_id_canonico)
        componentes.setdefault(raiz, []).append(item)

    agrupamento = {}
    for membros in componentes.values():
        ids_ordenados = sorted(i.item_id_canonico for i in membros)
        chave_hash = hashlib.sha256("|".join(ids_ordenados).encode()).hexdigest()[:24]
        agrupamento[chave_hash] = membros
    return agrupamento


def criar_nos_assunto(driver: Driver, agrupamento: dict[str, list[ItemPauta]]) -> None:
    for assunto_id, membros in agrupamento.items():
        if not any(i.assunto for i in membros):
            continue
        executar_escrita(driver, "MERGE (:Assunto {assunto_id: $assunto_id})", assunto_id=assunto_id)
        for item in membros:
            executar_escrita(
                driver,
                "MATCH (i:ItemPauta {item_id_canonico: $item_id}) "
                "MATCH (s:Assunto {assunto_id: $assunto_id}) "
                "MERGE (i)-[r:TRATA_DE]->(s) "
                "SET r.pagina = $pagina, r.trecho = $trecho",
                item_id=item.item_id_canonico, assunto_id=assunto_id,
                pagina=item.pagina_inicio, trecho=(item.assunto or "")[:500],
            )
