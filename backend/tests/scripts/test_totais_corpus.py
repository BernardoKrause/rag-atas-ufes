from datetime import date

from app.grafo.cliente import executar_escrita, obter_driver
from app.grafo.construtor import limpar_grafo
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta
from scripts.totais_corpus import formatar_tabela, totais_do_grafo, totais_dos_itens


def _documento(id_documento: int, orgao: str, paginas_ocr: list[int], texto: str = "texto") -> Documento:
    return Documento(
        id_documento=id_documento, nome_arquivo="x.pdf", url_origem="x.pdf", centro="CT", campus="Goiabeiras",
        tipo_orgao="B", orgao=orgao, data_reuniao=date(2025, 1, 1), texto_limpo=texto, paginas_ocr=paginas_ocr,
    )


def _item(item_id: str, fragmento_indice: int = 0, **campos) -> ItemPauta:
    return ItemPauta(
        item_id_canonico=item_id, documento_id=1, secao="PAUTA", numero_item="1", texto="x",
        fragmento_indice=fragmento_indice, **campos,
    )


def _corpus():
    documentos = [
        _documento(1, "CEUNES_DCAB", [1]),
        _documento(2, "CEUNES_DCAB", [2, 3]),
        _documento(3, "CT", [], texto="deﬁnição e gesơo"),
    ]
    itens = [
        _item("A", tipo_desfecho="Aprovado", ato_emitido="DECISAO_1_2025", encaminhamento="ao DCC"),
        _item("A_F1", fragmento_indice=1, tipo_desfecho="Aprovado", ato_emitido="DECISAO_1_2025",
              encaminhamento="ao DCC"),
        _item("B", tipo_desfecho="Aprovado", departamento_origem="DCC"),
        _item("C", tipo_desfecho=None),
        _item("D", tipo_desfecho="Retirado"),
    ]
    return documentos, itens


def test_totais_dos_itens_conta_por_item_logico():
    totais = totais_dos_itens(*_corpus())

    assert totais["atas"] == 3
    assert totais["linhas"] == 5
    assert totais["itens_logicos"] == 4
    assert totais["desfechos"] == {"Aprovado": 2, None: 1, "Retirado": 1}
    assert (totais["ato_emitido"], totais["departamento_origem"], totais["encaminhamento"]) == (1, 1, 1)


def test_totais_dos_itens_agrupa_atas_com_ocr_por_orgao():
    totais = totais_dos_itens(*_corpus())

    assert totais["atas_com_ocr"] == {"CEUNES_DCAB": 2}


def test_totais_dos_itens_conta_ligaduras_e_glifos_que_sobraram():
    totais = totais_dos_itens(*_corpus())

    assert totais["ligaduras"] == 2


def test_formatar_tabela_gera_as_linhas_do_relatorio():
    totais = {
        "atas": 357, "atas_com_ocr": {"CEUNES_DCAB": 12, "CEUNES": 3, "CCENS_DG": 1},
        "itens_logicos": 3362, "linhas": 3587, "janelas": 8947,
        "desfechos": {"Aprovado": 2253, None: 956, "Retirado": 141, "Reprovado": 9, "Encaminhado": 3},
        "ato_emitido": 67, "departamento_origem": 113, "encaminhamento": 32,
        "grafo": {"atas": 357, "deliberacoes": 2406, "encaminhamentos": 32, "processos": 1588,
                  "assuntos": 3053, "mesmo_assunto": 362},
        "ligaduras": 0,
    }

    tabela = formatar_tabela(totais)

    assert "| Atas | 357 |" in tabela
    assert "| Atas com páginas extraídas por OCR | 16 (CEUNES_DCAB 12, CEUNES 3, CCENS_DG 1) |" in tabela
    assert "| Itens de pauta lógicos / linhas com fragmentos | 3.362 / 3.587 |" in tabela
    assert "| Janelas no Qdrant | 8.947 |" in tabela
    assert (
        "| Desfecho por item lógico | Aprovado 2.253, sem desfecho 956, Retirado 141, Reprovado 9, Encaminhado 3 |"
        in tabela
    )
    assert "| Itens com ato emitido / departamento de origem / encaminhamento | 67 / 113 / 32 |" in tabela
    assert (
        "| Grafo | 357 atas, 2.406 deliberações, 32 encaminhamentos, 1.588 processos, 3.053 assuntos, "
        "362 relações `trata_do_mesmo_assunto` |" in tabela
    )
    assert "| Ligaduras ou glifos trocados no texto | 0 |" in tabela


def test_totais_do_grafo_conta_nos_e_relacoes():
    driver = obter_driver()
    try:
        limpar_grafo(driver)
        executar_escrita(
            driver,
            "CREATE (:Ata), (:Ata), (a:Deliberação)-[:trata_do_mesmo_assunto]->(b:Deliberação), "
            "(:Encaminhamento), (:Processo), (:Processo), (:Processo), (:Assunto)",
        )

        totais = totais_do_grafo(driver)

        assert totais == {
            "atas": 2, "deliberacoes": 2, "encaminhamentos": 1, "processos": 3, "assuntos": 1, "mesmo_assunto": 1,
        }
    finally:
        limpar_grafo(driver)
        driver.close()
