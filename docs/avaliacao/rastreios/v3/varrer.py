import json, re, sys, unicodedata
def norm(s): return unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode().lower()
STOP=set("o a os as de do da dos das e em no na nos nas foi foram para por com que se um uma ao aos sobre setor".split())
for l in open(sys.argv[1]):
    r=json.loads(l); resp=r["resposta"]
    if r["erro"] or resp["abstencao"]: print(f"P{r['n']} abst/erro"); continue
    fontes={f["numero"]:f for f in resp["fontes"]}
    for linha in resp["texto"].split("\n"):
        nums=[int(x) for x in re.findall(r"\[(\d+)\]", linha)]
        if not nums: continue
        trecho=norm(" ".join(fontes[n]["trecho"]+" "+fontes[n]["rotulo"] for n in nums if n in fontes))
        desc=re.sub(r"Resultado da votação:.*|Ato emitido:.*","",linha.split(": ",1)[-1])
        perg=norm(r["pergunta"])
        # termos da descrição que vêm da pergunta e não estão no trecho
        termos=[t for t in re.findall(r"[A-Za-zÀ-ú0-9/\.]{3,}", desc) if norm(t) not in STOP]
        faltam=sorted({t for t in termos if norm(t).strip('.') not in trecho and norm(t).strip('.') in perg})
        print(f"P{r['n']} [{r['situacao']}] fontes {nums} | faltam_no_trecho(da pergunta): {faltam}")
