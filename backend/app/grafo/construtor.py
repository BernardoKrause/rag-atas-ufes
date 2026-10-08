from __future__ import annotations

import hashlib
import re

from neo4j import Driver

from app.core.texto import remover_acentos_maiusculo
from app.grafo.cliente import executar_escrita, obter_driver
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
        SET a.nome_arquivo = $nome_arquivo, a.tipo_orgao = $tipo_orgao, a.status_aprovacao = $status_aprovacao
        MERGE (c:Centro {sigla: $centro})
        MERGE (a)-[:PERTENCE_A]->(c)
        MERGE (d:Data {valor: $data_reuniao})
        MERGE (a)-[:POSSUI]->(d)
        """,
        documento_id=documento.id_documento, nome_arquivo=documento.nome_arquivo,
        tipo_orgao=documento.tipo_orgao, centro=documento.centro,
        data_reuniao=documento.data_reuniao.isoformat(),
        status_aprovacao=documento.status_aprovacao,
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
            "MERGE (i)-[r:MENCIONA]->(p) "
            "SET r.pagina = $pagina, r.trecho = $trecho",
            item_id=item.item_id_canonico, token=token,
            pagina=item.pagina_inicio, trecho=item.texto[:500],
        )


class UnionFind:
    def __init__(self) -> None:
        self._pai: dict[str, str] = {}

    def find(self, x: str) -> str:
        self._pai.setdefault(x, x)
        raiz = x
        while self._pai[raiz] != raiz:
            raiz = self._pai[raiz]
        while self._pai[x] != raiz:
            self._pai[x], x = raiz, self._pai[x]
        return raiz

    def union(self, x: str, y: str) -> None:
        raiz_x, raiz_y = self.find(x), self.find(y)
        if raiz_x != raiz_y:
            self._pai[raiz_x] = raiz_y


def _normalizar_assunto(texto: str) -> str:
    sem_acento = remover_acentos_maiusculo(texto)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", sem_acento)).strip()


MIN_PALAVRAS_ASSUNTO = 3
MIN_CARACTERES_ASSUNTO = 20


def _assunto_e_sinal_util(chave: str) -> bool:
    """Assunto curto demais e residuo de segmentacao ("4", "PROC", "FOI
    APRECIADA E"), nao tema: usar como sinal fraco juntaria itens sem
    relacao nenhuma. Calibrado no corpus real — este corte descarta os 8
    grupos degenerados e preserva os 31 legitimos."""
    return len(chave) >= MIN_CARACTERES_ASSUNTO and len(chave.split()) >= MIN_PALAVRAS_ASSUNTO


def agrupar_assuntos(itens: list[ItemPauta]) -> dict[str, list[ItemPauta]]:
    """Componentes conectados: dois itens caem no mesmo Assunto se
    compartilham um token de Processo (sinal forte) ou tem assunto
    normalizado identico e suficientemente especifico (sinal fraco, risco de
    falso-positivo medido na validacao manual — ver Task 15)."""
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
            if _assunto_e_sinal_util(chave):
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


def criar_no_deliberacao(driver: Driver, item: ItemPauta) -> None:
    if item.tipo_desfecho is None:
        return
    executar_escrita(
        driver,
        """
        MATCH (i:ItemPauta {item_id_canonico: $item_id})
        MERGE (del:Deliberação {item_id_canonico: $item_id})
        SET del.tipo_desfecho = $tipo_desfecho, del.resultado_votacao = $resultado_votacao,
            del.ato_emitido = $ato_emitido, del.pagina = $pagina
        MERGE (i)-[:GERA]->(del)
        """,
        item_id=item.item_id_canonico, tipo_desfecho=item.tipo_desfecho,
        resultado_votacao=item.resultado_votacao, ato_emitido=item.ato_emitido,
        pagina=item.pagina_inicio,
    )
    if item.encaminhamento:
        executar_escrita(
            driver,
            "MATCH (del:Deliberação {item_id_canonico: $item_id}) "
            "MERGE (enc:Encaminhamento {item_id_canonico: $item_id}) "
            "SET enc.texto = $texto "
            "MERGE (del)-[:GERA]->(enc)",
            item_id=item.item_id_canonico, texto=item.encaminhamento,
        )


def _e_primeiro_fragmento(item: ItemPauta) -> bool:
    return (item.fragmento_indice or 0) == 0


def _chave_item_logico(item: ItemPauta) -> tuple:
    return (item.documento_id, item.secao, item.numero_item, item.ocorrencia_indice or 0)


def ligar_fragmento_a_deliberacao(driver: Driver, item: ItemPauta, deliberacao_item_id: str) -> None:
    executar_escrita(
        driver,
        "MATCH (i:ItemPauta {item_id_canonico: $item_id}) "
        "MATCH (del:Deliberação {item_id_canonico: $deliberacao_item_id}) "
        "MERGE (i)-[:GERA]->(del)",
        item_id=item.item_id_canonico, deliberacao_item_id=deliberacao_item_id,
    )


RE_CITACAO_DELIBERACAO = re.compile(
    r"(Revoga-se|Altera-se|Substitui-se)\s+a\s+(Resolu[çc][ãa]o|Decis[ãa]o)"
    r"(?:\s+[A-Z/]+)?\s+n?[º°.o]*\s*(\d+)(?:/(\d{4})|,\s*de\s+\d{1,2}\s+de\s+\w+\s+de\s+(\d{4}))",
    re.IGNORECASE,
)

_RELACAO_POR_VERBO = {"REVOGA-SE": "revoga", "ALTERA-SE": "altera", "SUBSTITUI-SE": "substitui"}


def resolver_citacoes_deliberacao(driver: Driver, itens: list[ItemPauta]) -> None:
    for item in itens:
        for match in RE_CITACAO_DELIBERACAO.finditer(item.texto):
            verbo = match.group(1).upper()
            tipo = "RESOLUCAO" if match.group(2).upper().startswith("RESOLU") else "DECISAO"
            numero = match.group(3)
            ano = match.group(4) or match.group(5)
            if ano is None:
                continue
            ato_citado = f"{tipo}_{int(numero)}_{ano}"
            relacao = _RELACAO_POR_VERBO[verbo]
            executar_escrita(
                driver,
                # ato_emitido nao e unico no corpus real; sem o LIMIT o MERGE
                # criaria uma aresta por no casado, e no maximo uma delas
                # apontaria pra deliberacao de fato citada.
                f"""
                MATCH (:ItemPauta {{item_id_canonico: $item_id}})-[:GERA]->(nova:Deliberação)
                MATCH (antiga:Deliberação {{ato_emitido: $ato_citado}})
                WITH nova, antiga ORDER BY antiga.item_id_canonico LIMIT 1
                MERGE (nova)-[:{relacao}]->(antiga)
                """,
                item_id=item.item_id_canonico, ato_citado=ato_citado,
            )


def criar_relacao_mesmo_assunto(driver: Driver, agrupamento: dict[str, list[ItemPauta]]) -> None:
    for membros in agrupamento.values():
        ids_com_deliberacao = [i.item_id_canonico for i in membros if i.tipo_desfecho is not None and _e_primeiro_fragmento(i)]
        pares = [
            {"id_a": id_a, "id_b": id_b}
            for i, id_a in enumerate(ids_com_deliberacao)
            for id_b in ids_com_deliberacao[i + 1:]
        ]
        if not pares:
            continue
        executar_escrita(
            driver,
            """
            UNWIND $pares AS par
            MATCH (a:Deliberação {item_id_canonico: par.id_a})
            MATCH (b:Deliberação {item_id_canonico: par.id_b})
            MERGE (a)-[:trata_do_mesmo_assunto]->(b)
            """,
            pares=pares,
        )


def construir_grafo(documentos_com_itens: list[tuple[Documento, list[ItemPauta]]], driver: Driver) -> None:
    limpar_grafo(driver)

    todos_itens = []
    primeiros: dict[tuple, ItemPauta] = {}
    for documento, itens in documentos_com_itens:
        criar_no_ata(driver, documento)
        for item in itens:
            criar_no_item(driver, documento.id_documento, item)
            if _e_primeiro_fragmento(item):
                criar_no_deliberacao(driver, item)
                primeiros[_chave_item_logico(item)] = item
            todos_itens.append(item)

    for item in todos_itens:
        primeiro = primeiros.get(_chave_item_logico(item))
        if not _e_primeiro_fragmento(item) and primeiro is not None and primeiro.tipo_desfecho is not None:
            ligar_fragmento_a_deliberacao(driver, item, primeiro.item_id_canonico)

    agrupamento = agrupar_assuntos(todos_itens)
    criar_nos_assunto(driver, agrupamento)
    resolver_citacoes_deliberacao(driver, todos_itens)
    criar_relacao_mesmo_assunto(driver, agrupamento)


def main() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings
    from app.models.consultas import carregar_documentos_com_itens

    engine = create_engine(settings.database_url)
    Sessao = sessionmaker(bind=engine)
    driver = obter_driver()

    try:
        with Sessao() as sessao:
            documentos_com_itens = carregar_documentos_com_itens(sessao)
            construir_grafo(documentos_com_itens, driver)
            print(f"grafo reconstruido a partir de {len(documentos_com_itens)} atas.")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
