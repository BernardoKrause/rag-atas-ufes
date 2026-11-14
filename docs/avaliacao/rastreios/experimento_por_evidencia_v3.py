import json
import re
import sys
from pathlib import Path

from app.geracao.llm import criar_cliente_llm

SISTEMA = """Você responde perguntas sobre atas de reuniões de órgãos colegiados da UFES \
usando exclusivamente as evidências fornecidas.

Cada evidência é um registro separado, com identificador, data da reunião e trecho.
Avalie cada evidência separadamente, na ordem em que aparecem, e devolva um registro \
para cada uma, em JSON. Uma evidência é relevante se registra algo sobre o assunto da \
pergunta, mesmo que seja curta (por exemplo, retirada de pauta ou adiamento).

Formato: {"eventos": [{"evidencia": <identificador>, "relevante": true|false, \
"descricao": "<o que ocorreu naquela reunião, incluindo a decisão ou o resultado da \
votação registrado, ou vazio se não for relevante>"}]}
Use apenas as evidências. Descreva só o que o trecho registra, sem inferir motivos, \
consequências ou ligações com outras reuniões. Responda em português."""


def main():
    rastreio = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    datas = {}
    blocos = []
    for e in rastreio["contexto_enviado"]:
        data = re.search(r"\d{2}/\d{2}/\d{4}", e["rotulo"]).group()
        datas[e["numero"]] = data
        blocos.append(json.dumps({"identificador": e["numero"], "data_reuniao": data,
                                  "fonte": e["rotulo"], "trecho": e["texto"]}, ensure_ascii=False))
    usuario = "Evidências:\n" + "\n".join(blocos) + f"\n\nPergunta: {rastreio['pergunta']}"
    saida = criar_cliente_llm().gerar(SISTEMA, usuario)
    print("BRUTA:", saida.texto)
    eventos = json.loads(re.search(r"\{.*\}", saida.texto, re.S).group())["eventos"]
    validos = [ev for ev in eventos if ev.get("evidencia") in datas and ev.get("relevante")]
    invalidos = [ev for ev in eventos if ev.get("evidencia") not in datas]
    print("irrelevantes:", [ev["evidencia"] for ev in eventos if not ev.get("relevante")])
    validos.sort(key=lambda ev: datas[ev["evidencia"]][6:] + datas[ev["evidencia"]][3:5] + datas[ev["evidencia"]][:2])
    for ev in validos:
        print(f"- {datas[ev['evidencia']]}: {ev['descricao']} [{ev['evidencia']}]")
    print("ids inválidos descartados:", invalidos)


if __name__ == "__main__":
    main()
