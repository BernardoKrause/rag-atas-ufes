from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.ingestion.enriquecedor import RE_ENCAMINHAMENTO_DOIS_PONTOS, RE_ENCAMINHAMENTO_DESTINO, extrair_encaminhamento
s = sessionmaker(bind=create_engine(settings.database_url))()
total = dentro = 0; exemplos = []
for iid, t in s.execute(text("select item_id_canonico, texto from itens_pauta")):
    enc = extrair_encaminhamento(t)
    if not enc:
        continue
    total += 1
    m = RE_ENCAMINHAMENTO_DOIS_PONTOS.search(t) or RE_ENCAMINHAMENTO_DESTINO.search(t)
    antes = t[:m.start()]
    abertas = antes.count("“") + antes.count('"') % 2 * 0
    if antes.count("“") > antes.count("”"):
        dentro += 1; exemplos.append((iid, t[max(0, m.start()-120):m.start()+60].replace("\n", " ")))
print("itens com encaminhamento extraído:", total, "| dentro de aspas abertas:", dentro)
for e in exemplos[:12]: print("-", e)
