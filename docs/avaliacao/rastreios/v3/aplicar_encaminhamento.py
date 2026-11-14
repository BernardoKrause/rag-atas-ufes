import json
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.ingestion.enriquecedor import enriquecer_item, reconstruir_texto_do_item
from app.models.consultas import carregar_documentos_com_itens

ESPERADO_MUDANCAS = 17
s = sessionmaker(bind=create_engine(settings.database_url))()
mudancas, divergentes = [], 0
for doc, itens in carregar_documentos_com_itens(s):
    grupos = {}
    for i in itens:
        grupos.setdefault((i.secao, i.numero_item, i.ocorrencia_indice), []).append(i)
    for fr in grupos.values():
        fr.sort(key=lambda f: f.fragmento_indice)
        texto = reconstruir_texto_do_item([f.texto for f in fr])
        campos = enriquecer_item(doc.tipo_orgao, doc.centro, texto, doc.data_reuniao, secao=fr[0].secao)
        divergentes += any(
            getattr(campos, c) != getattr(fr[0], c)
            for c in ("assunto", "tipo_desfecho", "resultado_votacao", "ato_emitido", "departamento_origem")
        )
        if campos.encaminhamento != fr[0].encaminhamento:
            mudancas.append({"item": fr[0].item_id_canonico, "fragmentos": len(fr),
                             "antes": fr[0].encaminhamento, "depois": campos.encaminhamento})
            for f in fr:
                f.encaminhamento = campos.encaminhamento
assert divergentes == 0, f"outros campos divergem: {divergentes}"
assert len(mudancas) == ESPERADO_MUDANCAS, f"mudanças inesperadas: {len(mudancas)}"
json.dump(mudancas, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
s.commit()
print("itens lógicos alterados:", len(mudancas), "| linhas:", sum(m["fragmentos"] for m in mudancas))
