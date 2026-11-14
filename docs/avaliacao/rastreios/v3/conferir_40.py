import csv, json, re, sys
from datetime import datetime
A = "/Users/bk/Documents/Projects/RAG ATAS UFES - TCC/deploy_bernardo/amostra_personas_40/gabarito.csv"
gab = {r["n"]: r for r in csv.DictReader(open(A, encoding="utf-8-sig"), delimiter=";")}
resumo = {"todas": 0, "parte": 0, "nenhuma": 0, "abstencao": 0, "erro": 0}
for linha in open(sys.argv[1]):
    r = json.loads(linha); g = gab[r["n"]]
    esperadas = set(re.findall(r"\d{4}-\d{2}-\d{2}", g["fontes_referencia"]))
    if r["erro"]:
        resumo["erro"] += 1; print(f"P{r['n']} ERRO {r['erro']}"); continue
    resp = r["resposta"]
    citadas = {datetime.strptime(d, "%d/%m/%Y").strftime("%Y-%m-%d") for f in resp["fontes"] for d in re.findall(r"\d{2}/\d{2}/\d{4}", f["rotulo"])[:1]}
    if resp["abstencao"]:
        classe = "abstencao"
    else:
        achadas = esperadas & citadas
        classe = "todas" if achadas == esperadas else "parte" if achadas else "nenhuma"
    resumo[classe] += 1
    print(f"P{r['n']} [{r['situacao']}] {r['segundos']}s {classe.upper()} | esperadas {sorted(esperadas)} | citadas {sorted(citadas)}")
    if "--texto" in sys.argv:
        print("   RAG:", resp["texto"][:500].replace("\n", " ⏎ "))
        print("   REF:", g["resposta_referencia"][:300].replace("\n", " "))
print(resumo)
