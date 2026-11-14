import csv, json, sys, time, urllib.request
A = "/Users/bk/Documents/Projects/RAG ATAS UFES - TCC/deploy_bernardo/amostra_personas_40/perguntas.csv"
saida = sys.argv[1]
feitos = set()
try:
    feitos = {json.loads(l)["n"] for l in open(saida)}
except FileNotFoundError:
    pass
for r in csv.DictReader(open(A, encoding="utf-8-sig"), delimiter=";"):
    if r["n"] in feitos:
        continue
    inicio = time.time()
    try:
        pedido = urllib.request.Request("http://localhost:8001/consultas", data=json.dumps({"pergunta": r["pergunta"]}).encode(),
                                        headers={"Content-Type": "application/json"})
        corpo = json.load(urllib.request.urlopen(pedido, timeout=900)); erro = None
    except Exception as e:
        corpo, erro = None, repr(e)
    with open(saida, "a") as f:
        f.write(json.dumps({"n": r["n"], "situacao": r["situacao"], "setor": r["setor"], "pergunta": r["pergunta"],
                            "segundos": round(time.time() - inicio), "erro": erro, "resposta": corpo}, ensure_ascii=False) + "\n")
    print(f"P{r['n']} {round(time.time()-inicio)}s {'ERRO' if erro else ('abstenção' if corpo['abstencao'] else str(len(corpo['fontes']))+' fontes')}", flush=True)
