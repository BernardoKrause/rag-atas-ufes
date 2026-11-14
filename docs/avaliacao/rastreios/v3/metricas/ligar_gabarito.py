import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, text

from app.core.config import settings

GABARITO = Path(sys.argv[1])
SAIDA = Path(sys.argv[2])
REGISTRO = re.compile(r"Registro de (\d\d/\d\d/\d{4}) — ([^(\n]+?) \(([^)]*)\):")


def normalizar_numero(numero):
    return ".".join(str(int(p)) if p.isdigit() else p for p in str(numero).strip().rstrip(".").split("."))


def main():
    linhas = list(csv.DictReader(GABARITO.open(encoding="utf-8-sig"), delimiter=";"))
    motor = create_engine(settings.database_url)
    saida = []
    with motor.connect() as conexao:
        for linha in linhas:
            registros = []
            for data, orgao, local in REGISTRO.findall(linha["resposta_referencia"]):
                secao, numero = [p.strip() for p in local.rsplit(", item ", 1)]
                data_iso = datetime.strptime(data, "%d/%m/%Y").date().isoformat()
                candidatos = conexao.execute(
                    text(
                        "select i.item_id_canonico, i.numero_item, i.secao, i.fragmento_indice, "
                        "i.ocorrencia_indice from itens_pauta i join documentos d "
                        "on d.id_documento = i.documento_id where d.orgao = :orgao "
                        "and d.data_reuniao = :data and upper(i.secao) = upper(:secao)"
                    ),
                    {"orgao": orgao.strip(), "data": data_iso, "secao": secao},
                ).all()
                exatos = [c for c in candidatos if c.numero_item == numero and not c.fragmento_indice]
                if not exatos:
                    exatos = [
                        c for c in candidatos
                        if normalizar_numero(c.numero_item) == normalizar_numero(numero)
                        and not c.fragmento_indice
                    ]
                ligacao = "exata"
                if not exatos and "." in numero:
                    pai = numero.split(".", 1)[0]
                    exatos = [
                        c for c in candidatos
                        if normalizar_numero(c.numero_item) == normalizar_numero(pai)
                        and not c.fragmento_indice
                    ]
                    ligacao = "item_pai"
                registros.append({
                    "data": data_iso, "orgao": orgao.strip(), "secao": secao, "numero": numero,
                    "ligacao": ligacao, "itens": sorted(c.item_id_canonico for c in exatos),
                })
            saida.append({"n": linha["n"], "situacao": linha["situacao"], "registros": registros})
    SAIDA.write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in saida) + "\n", encoding="utf-8")
    ruins = [(s["n"], r) for s in saida for r in s["registros"] if len(r["itens"]) != 1]
    print(f"{sum(len(s['registros']) for s in saida)} registros; {len(ruins)} sem ligação única")
    for n, r in ruins:
        print(n, r)


if __name__ == "__main__":
    main()
