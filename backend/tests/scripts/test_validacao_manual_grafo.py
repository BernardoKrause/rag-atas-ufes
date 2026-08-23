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
