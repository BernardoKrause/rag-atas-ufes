from __future__ import annotations

import hashlib
import re
from datetime import date

from neo4j import Driver

from app.core.texto import remover_acentos_maiusculo
from app.grafo.cliente import executar_escrita, executar_leitura, obter_driver
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
        SET a.nome_arquivo = $nome_arquivo, a.tipo_orgao = $tipo_orgao, a.status_aprovacao = $status_aprovacao,
            a.orgao = $orgao
        MERGE (c:Centro {sigla: $centro})
        MERGE (a)-[:PERTENCE_A]->(c)
        MERGE (d:Data {valor: $data_reuniao})
        MERGE (a)-[:POSSUI]->(d)
        """,
        documento_id=documento.id_documento, nome_arquivo=documento.nome_arquivo,
        tipo_orgao=documento.tipo_orgao, orgao=documento.orgao, centro=documento.centro,
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


RE_TOKEN_PESSOA = re.compile(r"PESSOA_\d+")
RE_LISTA_DE_PAUTA = re.compile(
    r"INCLUS(?:[AÃ]O|[OÕ]ES)|EXCLUS(?:[AÃ]O|[OÕ]ES)|INVERS(?:[AÃ]O|[OÕ]ES)|ORDEM D[AO] (?:DIA|PAUTA)", re.IGNORECASE
)
SECOES_DE_LISTA = {"EXPEDIENTE", "EXCLUSÃO DE PAUTA", "COMUNICAÇÕES", "INFORMES"}

RE_MARCADOR_ITEM = re.compile(
    r"^\s*(?:\[\d+\]|(?:PAUTA|INFORMES?)\s*\d+\s*:|PONTO\s+(?:\d+(?:\.\d+)?|[UÚ]NICO)\s*[-–:]?"
    r"|\d{1,2}(?:\.\d{1,2})*\s*[.)–-]?)\s*",
    re.IGNORECASE,
)
RE_PREFIXO_PROCESSO = re.compile(
    r"^(?:(?:PROCESSO DIGITAL|PROC\.? DIGITAL|DOCUMENTO AVULSO|DOC\.? AVULSO|PROCESSO|PROC\.?|PROT(?:OC)?\.?)"
    r"\s*(?:N[º°O.]*\s*)?(?:PROCESSO_\d+)?\s*[-–.:]?\s*)+",
    re.IGNORECASE,
)
RE_FIM_DO_TITULO = re.compile(
    r"(?<!\bprof)(?<!\bprofa)(?<!\bdr)(?<!\bdra)(?<!\bdrª)(?<!\bsr)(?<!\bsra)(?<!\bn)(?<!\bnº)(?<!\bart)"
    r"\.\s|\s[-–]\s|:\s",
    re.IGNORECASE,
)
RE_TITULO_GENERICO = re.compile(
    r"^(?:FOI|FORAM|EM|APOS|O|A|OS|AS|INCLUSAO|EXCLUSAO|INVERSAO|RETIRADA|NAO HOUVE)\b"
    r"|^(?:DEPARTAMENTO|CENTRO|COORDENACAO|COLEGIADO|PROGRAMA|INTERESSAD[OA])\b(?:\s+\S+){0,5}$"
)
MIN_PALAVRAS_TITULO = 6
MAX_PALAVRAS_TITULO = 30
JANELA_TITULO_DIAS = 300
JANELA_PEDIDO_DIAS = 548

PEDIDOS_DE_PESSOA = (
    ("LICENCA", re.compile(r"LICENCA\s+(?:PARA\s+)?CAPACITA\w*")),
    ("AFASTAMENTO", re.compile(
        r"AFASTAMENTO\s+(?:\w+\s+){0,3}(?:POS\s*-?\s*DOUTOR\w*|DOUTORADO|MESTRADO|CAPACITA\w*|QUALIFICA\w*)"
    )),
)
ALCANCE_PESSOA = 80
ALCANCE_PEDIDO = 500


def processo_principal(texto: str, secao: str) -> str | None:
    processos = list(dict.fromkeys(RE_TOKEN_PROCESSO.findall(texto)))
    if not processos or len(processos) >= 3:
        return None
    if len(processos) == 2 and (secao in SECOES_DE_LISTA or RE_LISTA_DE_PAUTA.search(texto[:400])):
        return None
    return processos[0]


def titulo_do_item(texto: str) -> str:
    restante = RE_PREFIXO_PROCESSO.sub("", RE_MARCADOR_ITEM.sub("", texto, count=1), count=1)
    restante = RE_TOKEN_PROCESSO.sub(" ", restante)
    primeira_frase = RE_FIM_DO_TITULO.split(restante, maxsplit=1)[0]
    palavras = re.sub(r"[^\w\s]", " ", remover_acentos_maiusculo(primeira_frase)).split()
    return " ".join(palavras[:MAX_PALAVRAS_TITULO])


def _titulo_util(titulo: str) -> bool:
    palavras = titulo.split()
    if len(palavras) < MIN_PALAVRAS_TITULO or RE_TITULO_GENERICO.search(titulo):
        return False
    return not re.search(r"\bATAS?\b", " ".join(palavras[:10]))


RE_ROTULO_RELATOR = re.compile(
    r"(?:RELATOR\w*|PARECER\w*)(?:\(A\))?(?:\W+(?:CONSELHEIR[OA]|PROF\w*|DR\w*|SR\w*|FAVORAVEL|D[AEO]))*\W{0,6}$"
)
ALCANCE_ROTULO = 45


def _pessoas_sem_relator(texto: str, inicio: int, fim: int) -> list[str]:
    return [
        m.group(0) for m in RE_TOKEN_PESSOA.finditer(texto)
        if max(inicio, 0) <= m.start() < fim
        and not RE_ROTULO_RELATOR.search(texto[max(0, m.start() - ALCANCE_ROTULO):m.start()])
    ]


def pedidos_de_pessoa(texto: str) -> set[tuple[str, str]]:
    normalizado = remover_acentos_maiusculo(texto)
    pedidos = set()
    for nome, padrao in PEDIDOS_DE_PESSOA:
        for match in padrao.finditer(normalizado):
            if match.start() >= ALCANCE_PEDIDO:
                break
            depois = _pessoas_sem_relator(normalizado, match.end(), match.end() + ALCANCE_PESSOA)
            antes = _pessoas_sem_relator(normalizado, match.start() - ALCANCE_PESSOA, match.start())
            pessoa = depois[0] if depois else (antes[-1] if antes else None)
            if pessoa:
                pedidos.add((nome, pessoa))
    return pedidos


def _um_prefixo_do_outro(a: str, b: str) -> bool:
    curto, longo = sorted((a.split(), b.split()), key=len)
    return longo[:len(curto)] == curto


def _dentro_da_janela(data_a: date | None, data_b: date | None, dias: int) -> bool:
    return data_a is None or data_b is None or abs((data_b - data_a).days) <= dias


def agrupar_assuntos(
    itens: list[ItemPauta], contexto: dict[int, tuple[str, date]] | None = None
) -> dict[str, list[ItemPauta]]:
    contexto = contexto or {}
    uniao = UnionFind()
    por_item_logico: dict[tuple, list[ItemPauta]] = {}
    for item in itens:
        uniao.find(item.item_id_canonico)
        por_item_logico.setdefault(_chave_item_logico(item), []).append(item)

    logicos = []
    for fragmentos in por_item_logico.values():
        fragmentos.sort(key=lambda i: i.fragmento_indice or 0)
        for outro in fragmentos[1:]:
            uniao.union(fragmentos[0].item_id_canonico, outro.item_id_canonico)
        texto = " ".join(f.texto or "" for f in fragmentos)
        orgao, data = contexto.get(fragmentos[0].documento_id, ("", None))
        logicos.append({
            "id": fragmentos[0].item_id_canonico, "orgao": orgao, "data": data,
            "processo": processo_principal(texto, fragmentos[0].secao),
            "titulo": titulo_do_item(fragmentos[0].texto or ""),
            "pedidos": set() if RE_LISTA_DE_PAUTA.search(texto[:400]) else pedidos_de_pessoa(fragmentos[0].texto or ""),
        })

    por_processo: dict[str, list[dict]] = {}
    for logico in logicos:
        if logico["processo"]:
            por_processo.setdefault(logico["processo"], []).append(logico)
    for grupo in por_processo.values():
        for outro in grupo[1:]:
            uniao.union(grupo[0]["id"], outro["id"])

    processos_do_componente: dict[str, set[str]] = {}
    for logico in logicos:
        if logico["processo"]:
            processos_do_componente.setdefault(uniao.find(logico["id"]), set()).add(logico["processo"])

    def unir_sem_conflito(a: str, b: str) -> None:
        raiz_a, raiz_b = uniao.find(a), uniao.find(b)
        if raiz_a == raiz_b:
            return
        processos_a = processos_do_componente.get(raiz_a, set())
        processos_b = processos_do_componente.get(raiz_b, set())
        if processos_a and processos_b and processos_a != processos_b:
            return
        uniao.union(a, b)
        processos_do_componente[uniao.find(a)] = processos_a | processos_b

    por_titulo: dict[tuple, list[dict]] = {}
    for logico in logicos:
        if _titulo_util(logico["titulo"]):
            chave = (logico["orgao"], " ".join(logico["titulo"].split()[:MIN_PALAVRAS_TITULO]))
            por_titulo.setdefault(chave, []).append(logico)
    for grupo in por_titulo.values():
        grupo.sort(key=lambda logico: (logico["data"] or date.min, logico["id"]))
        for j, atual in enumerate(grupo):
            for anterior in reversed(grupo[:j]):
                if not _dentro_da_janela(anterior["data"], atual["data"], JANELA_TITULO_DIAS):
                    break
                if _um_prefixo_do_outro(anterior["titulo"], atual["titulo"]):
                    unir_sem_conflito(anterior["id"], atual["id"])
                    break

    por_pedido: dict[tuple, list[dict]] = {}
    for logico in logicos:
        for pedido in logico["pedidos"]:
            por_pedido.setdefault((logico["orgao"], *pedido), []).append(logico)
    for grupo in por_pedido.values():
        grupo.sort(key=lambda logico: (logico["data"] or date.min, logico["id"]))
        for anterior, atual in zip(grupo, grupo[1:]):
            if _dentro_da_janela(anterior["data"], atual["data"], JANELA_PEDIDO_DIAS):
                uniao.union(anterior["id"], atual["id"])

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
    r"(Revoga-se|Altera-se|Substitui-se|revoga[çc][ãa]o|revogar|altera[çc][ãa]o|substitui[çc][ãa]o)"
    r"\s+(?:a|da|de)\s+(Resolu[çc][ãa]o|Decis[ãa]o)"
    r"(?:\s+[A-Z/]+)?\s+n?[º°.o]*\s*(\d+)(?:/(\d{4})|,\s*de\s+\d{1,2}\s+de\s+\w+\s+de\s+(\d{4}))",
    re.IGNORECASE,
)


def _relacao_do_verbo(verbo: str) -> str:
    verbo = remover_acentos_maiusculo(verbo)
    if verbo.startswith("REVOG"):
        return "revoga"
    if verbo.startswith("ALTER"):
        return "altera"
    return "substitui"


def citacoes_de_atos(texto: str) -> list[tuple[str, str]]:
    citacoes = []
    for match in RE_CITACAO_DELIBERACAO.finditer(texto):
        ano = match.group(4) or match.group(5)
        tipo = "RESOLUCAO" if remover_acentos_maiusculo(match.group(2)).startswith("RESOLU") else "DECISAO"
        citacao = (_relacao_do_verbo(match.group(1)), f"{tipo}_{int(match.group(3))}_{ano}")
        if citacao not in citacoes:
            citacoes.append(citacao)
    return citacoes


def _textos_por_item_logico(itens: list[ItemPauta]) -> list[tuple[ItemPauta, str]]:
    por_item: dict[tuple, list[ItemPauta]] = {}
    for item in itens:
        por_item.setdefault(_chave_item_logico(item), []).append(item)
    resultado = []
    for fragmentos in por_item.values():
        fragmentos.sort(key=lambda i: i.fragmento_indice or 0)
        resultado.append((fragmentos[0], " ".join(f.texto or "" for f in fragmentos)))
    return resultado


def resolver_citacoes_deliberacao(
    driver: Driver, itens: list[ItemPauta], contexto: dict[int, tuple[str, date]] | None = None
) -> tuple[int, int]:
    contexto = contexto or {}
    total = ligadas = 0
    for primeiro, texto in _textos_por_item_logico(itens):
        orgao = contexto.get(primeiro.documento_id, (None, None))[0]
        for relacao, ato_citado in citacoes_de_atos(texto):
            total += 1
            linhas = executar_leitura(
                driver,
                # ato_emitido nao e unico no corpus real; sem o LIMIT o MERGE
                # criaria uma aresta por no casado, e no maximo uma delas
                # apontaria pra deliberacao de fato citada.
                f"""
                MATCH (:ItemPauta {{item_id_canonico: $item_id}})-[:GERA]->(nova:Deliberação)
                MATCH (ata:Ata)-[:CONTEM]->(:ItemPauta)-[:GERA]->(antiga:Deliberação {{ato_emitido: $ato_citado}})
                WHERE $orgao IS NULL OR ata.orgao = $orgao
                WITH nova, antiga ORDER BY antiga.item_id_canonico LIMIT 1
                MERGE (nova)-[:{relacao}]->(antiga)
                RETURN count(*) AS criadas
                """,
                item_id=primeiro.item_id_canonico, ato_citado=ato_citado, orgao=orgao,
            )
            ligadas += 1 if linhas and linhas[0]["criadas"] else 0
    return total, ligadas


RE_RETIFICACAO_ATA = re.compile(
    r"\bretifica\w*\s+(?:d[ao]s?\s+)?(?:excerto\s+de\s+)?ata\b|\bata\s+retificada\b", re.IGNORECASE
)
RE_DATA_NUMERICA = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)")
RE_REUNIAO_NUMERO_ANO = re.compile(
    r"(\d{1,2})\s*[ªaº°]\s+(?:reuni[ãa]o|sess[ãa]o)\s+ordin[áa]ria\s+de\s+(\d{4})", re.IGNORECASE
)
ALCANCE_RETIFICACAO = 160


def citacoes_de_retificacao(texto: str) -> list[tuple[date | None, tuple[int, int] | None]]:
    citacoes = []
    for match in RE_RETIFICACAO_ATA.finditer(texto):
        trecho = texto[match.end():match.end() + ALCANCE_RETIFICACAO]
        data = RE_DATA_NUMERICA.search(trecho)
        if data:
            try:
                citacao = (date(int(data.group(3)), int(data.group(2)), int(data.group(1))), None)
            except ValueError:
                continue
        else:
            numero_ano = RE_REUNIAO_NUMERO_ANO.search(trecho)
            if not numero_ano:
                continue
            citacao = (None, (int(numero_ano.group(1)), int(numero_ano.group(2))))
        if citacao not in citacoes:
            citacoes.append(citacao)
    return citacoes


def criar_relacoes_retificacao(
    driver: Driver, itens: list[ItemPauta], documentos: list[Documento]
) -> tuple[int, int]:
    por_data = {(d.orgao, d.data_reuniao): d.id_documento for d in documentos}
    por_numero = {
        (d.orgao, d.numero_reuniao, d.data_reuniao.year): d.id_documento
        for d in documentos
        if d.numero_reuniao and (d.tipo_reuniao or "").lower().startswith("ordin")
    }
    orgao_do_documento = {d.id_documento: d.orgao for d in documentos}
    total = ligadas = 0
    for primeiro, texto in _textos_por_item_logico(itens):
        orgao = orgao_do_documento.get(primeiro.documento_id)
        for data, numero_ano in citacoes_de_retificacao(texto):
            total += 1
            alvo = por_data.get((orgao, data)) if data else por_numero.get((orgao, *numero_ano))
            if alvo is None or alvo == primeiro.documento_id:
                continue
            ligadas += 1
            executar_escrita(
                driver,
                "MATCH (i:ItemPauta {item_id_canonico: $item_id}) "
                "MATCH (a:Ata {documento_id: $documento_id}) "
                "MERGE (i)-[:RETIFICA]->(a)",
                item_id=primeiro.item_id_canonico, documento_id=alvo,
            )
    return total, ligadas


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


def construir_grafo(documentos_com_itens: list[tuple[Documento, list[ItemPauta]]], driver: Driver) -> dict:
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

    contexto = {documento.id_documento: (documento.orgao, documento.data_reuniao) for documento, _ in documentos_com_itens}
    agrupamento = agrupar_assuntos(todos_itens, contexto)
    criar_nos_assunto(driver, agrupamento)
    citacoes_atos, atos_ligados = resolver_citacoes_deliberacao(driver, todos_itens, contexto)
    citacoes_retificacao, retificacoes_ligadas = criar_relacoes_retificacao(
        driver, todos_itens, [documento for documento, _ in documentos_com_itens]
    )
    criar_relacao_mesmo_assunto(driver, agrupamento)
    return {
        "citacoes_de_atos": citacoes_atos, "atos_no_grafo": atos_ligados,
        "citacoes_de_retificacao": citacoes_retificacao, "retificacoes_no_grafo": retificacoes_ligadas,
    }


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
            resumo = construir_grafo(documentos_com_itens, driver)
            print(f"grafo reconstruido a partir de {len(documentos_com_itens)} atas.")
            print(
                f"citacoes de atos: {resumo['citacoes_de_atos']} ({resumo['atos_no_grafo']} com o ato no grafo); "
                f"retificacoes de ata: {resumo['citacoes_de_retificacao']} "
                f"({resumo['retificacoes_no_grafo']} com a ata no grafo)."
            )
    finally:
        driver.close()


if __name__ == "__main__":
    main()
