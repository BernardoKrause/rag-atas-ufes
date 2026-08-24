from datetime import date

from app.models.documento import Documento
from app.models.item_pauta import ItemPauta
from scripts.validacao_manual_grafo import amostrar_itens


def _documento(id_documento: int, tipo_orgao: str, centro: str) -> Documento:
    return Documento(
        id_documento=id_documento, nome_arquivo="x.pdf", url_origem="x.pdf", centro=centro,
        campus="Goiabeiras", tipo_orgao=tipo_orgao, orgao=centro, data_reuniao=date(2025, 1, 1),
        texto_limpo="texto",
    )


def test_amostrar_itens_respeita_n_por_variante():
    doc_ct = _documento(1, "B", "CT")
    doc_car = _documento(2, "B", "CAR")

    pares = [
        (doc_ct, ItemPauta(item_id_canonico=f"A{i}", documento_id=1, secao="PAUTA", numero_item=str(i), texto="x"))
        for i in range(5)
    ] + [
        (doc_car, ItemPauta(item_id_canonico=f"B{i}", documento_id=2, secao="PAUTA", numero_item=str(i), texto="x"))
        for i in range(3)
    ]

    amostra = amostrar_itens(pares, n_por_variante=2)

    assert len([p for p in amostra if p[1].item_id_canonico.startswith("A")]) == 2
    assert len([p for p in amostra if p[1].item_id_canonico.startswith("B")]) == 2


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
    amostra = amostrar_itens(_pares_com_raros(), n_por_variante=5)
    ids = {item.item_id_canonico for _, item in amostra}

    assert {"ATO1", "ATO2"} <= ids
    assert {"DEP1", "DEP2"} <= ids
    assert {"REPROVADO1", "ADIADO1"} <= ids


def test_amostrar_itens_nao_repete_item_entre_estratos():
    amostra = amostrar_itens(_pares_com_raros(), n_por_variante=5)
    ids = [item.item_id_canonico for _, item in amostra]

    assert len(ids) == len(set(ids))


def test_amostrar_itens_limita_estrato_suplementar():
    from scripts.validacao_manual_grafo import LIMITE_ESTRATO_SUPLEMENTAR

    doc = _documento(1, "B", "CT")
    pares = [(doc, _item(f"ATO{i}", ato_emitido=f"DECISAO_{i}_2025")) for i in range(40)]

    amostra = amostrar_itens(pares, n_por_variante=5)

    assert len(amostra) == 5 + LIMITE_ESTRATO_SUPLEMENTAR


def test_amostrar_itens_e_deterministica():
    pares = _pares_com_raros()
    primeira = [i.item_id_canonico for _, i in amostrar_itens(pares, n_por_variante=5)]
    segunda = [i.item_id_canonico for _, i in amostrar_itens(pares, n_por_variante=5)]

    assert primeira == segunda
