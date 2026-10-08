from datetime import date

from app.models.documento import Documento
from app.models.item_pauta import ItemPauta
from scripts.validacao_manual_grafo import amostrar_itens, filtrar_por_ids, gerar_linha_csv


def _documento(id_documento: int, tipo_orgao: str, centro: str) -> Documento:
    return Documento(
        id_documento=id_documento, nome_arquivo="x.pdf", url_origem="x.pdf", centro=centro,
        campus="Goiabeiras", tipo_orgao=tipo_orgao, orgao=centro, data_reuniao=date(2025, 1, 1),
        texto_limpo="texto",
    )


def _pares_da_variante(tipo: str, centro: str, id_documento: int, quantidade: int):
    doc = _documento(id_documento, tipo, centro)
    return [
        (doc, ItemPauta(
            item_id_canonico=f"{tipo}{centro}{i}", documento_id=id_documento, secao="PAUTA",
            numero_item=str(i), texto="x",
        ))
        for i in range(quantidade)
    ]


def test_amostrar_itens_respeita_n_por_tipo():
    pares = (
        _pares_da_variante("A", "CCAE", 1, 30)
        + _pares_da_variante("B", "CT", 2, 30)
        + _pares_da_variante("B", "CCE", 3, 30)
    )

    amostra = amostrar_itens(pares, n_por_tipo=4)

    assert len([p for p in amostra if p[0].tipo_orgao == "A"]) == 4
    assert len([p for p in amostra if p[0].tipo_orgao == "B"]) == 4


def test_amostrar_itens_distribui_entre_variantes_do_tipo():
    pares = _pares_da_variante("B", "CCE", 1, 100) + _pares_da_variante("B", "CT", 2, 5)

    amostra = amostrar_itens(pares, n_por_tipo=4)

    assert len([p for p in amostra if p[0].centro == "CCE"]) == 2
    assert len([p for p in amostra if p[0].centro == "CT"]) == 2


def test_amostrar_itens_completa_com_outra_variante_quando_uma_esgota():
    pares = _pares_da_variante("D", "CE", 1, 1) + _pares_da_variante("D", "CCHN", 2, 10)

    amostra = amostrar_itens(pares, n_por_tipo=5)

    assert len(amostra) == 5
    assert len([p for p in amostra if p[0].centro == "CE"]) == 1


def test_gerar_linha_csv_marca_ocr_quando_pagina_do_item_veio_de_ocr():
    doc = _documento(1, "A", "CEUNES")
    doc.paginas_ocr = [2, 3]
    item = ItemPauta(
        item_id_canonico="X", documento_id=1, secao="PAUTA", numero_item="1", texto="x",
        pagina_inicio=1, pagina_fim=2,
    )

    assert gerar_linha_csv(doc, item, [], [])["ocr"] == "sim"

    item.pagina_fim = 1
    assert gerar_linha_csv(doc, item, [], [])["ocr"] == "nao"


def test_filtrar_por_ids_mantem_so_os_itens_pedidos():
    pares = _pares_da_variante("A", "CCAE", 1, 5)

    filtrados = filtrar_por_ids(pares, {"ACCAE1", "ACCAE3"})

    assert [p[1].item_id_canonico for p in filtrados] == ["ACCAE1", "ACCAE3"]


def _item(sufixo: str, **campos) -> ItemPauta:
    return ItemPauta(
        item_id_canonico=sufixo, documento_id=1, secao="PAUTA", numero_item="1", texto="x", **campos
    )


def _pares_com_raros() -> list[tuple[Documento, ItemPauta]]:
    doc = _documento(1, "B", "CT")
    comuns = [(doc, _item(f"COMUM{i}", tipo_desfecho="Aprovado")) for i in range(60)]
    raros = [
        (doc, _item("ATO1", ato_emitido="RESOLUCAO_79_2025")),
        (doc, _item("ATO2", ato_emitido="DECISAO_3_2025")),
        (doc, _item("DEP1", departamento_origem="INFORMATICA")),
        (doc, _item("DEP2", departamento_origem="ENGENHARIA_CIVIL")),
        (doc, _item("REPROVADO1", tipo_desfecho="Reprovado")),
        (doc, _item("ADIADO1", tipo_desfecho="Adiado")),
    ]
    return comuns + raros


def test_amostrar_itens_inclui_estratos_suplementares_raros():
    amostra = amostrar_itens(_pares_com_raros(), n_por_tipo=5)
    ids = {item.item_id_canonico for _, item in amostra}

    assert {"ATO1", "ATO2"} <= ids
    assert {"DEP1", "DEP2"} <= ids
    assert {"REPROVADO1", "ADIADO1"} <= ids


def test_amostrar_itens_nao_repete_item_entre_estratos():
    amostra = amostrar_itens(_pares_com_raros(), n_por_tipo=5)
    ids = [item.item_id_canonico for _, item in amostra]

    assert len(ids) == len(set(ids))


def test_amostrar_itens_limita_estrato_suplementar():
    from scripts.validacao_manual_grafo import LIMITE_ESTRATO_SUPLEMENTAR

    doc = _documento(1, "B", "CT")
    pares = [(doc, _item(f"ATO{i}", ato_emitido=f"DECISAO_{i}_2025")) for i in range(40)]

    amostra = amostrar_itens(pares, n_por_tipo=5)

    assert len(amostra) == 5 + LIMITE_ESTRATO_SUPLEMENTAR


def test_amostrar_itens_e_deterministica():
    pares = _pares_com_raros()
    primeira = [i.item_id_canonico for _, i in amostrar_itens(pares, n_por_tipo=5)]
    segunda = [i.item_id_canonico for _, i in amostrar_itens(pares, n_por_tipo=5)]

    assert primeira == segunda


def test_exportar_csv_sem_linhas_nao_levanta_nem_grava(tmp_path, capsys):
    from scripts.validacao_manual_grafo import exportar_csv

    destino = tmp_path / "saida.csv"
    exportar_csv(destino, [])

    assert not destino.exists()
    assert "nenhum item" in capsys.readouterr().out.lower()
