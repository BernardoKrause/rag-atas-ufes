import json, re, sys, unicodedata

def norm(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()

RE_TERMO = re.compile(r"\b(?:[A-Z]{2,}[A-Z0-9_]*|\w*\d\w*(?:[./-]\w+)*|(?:[A-ZÀ-Ú][a-zà-ú]+)(?:\s+(?:de|do|da|dos|das|e)?\s*[A-ZÀ-Ú][a-zà-ú]+)+)\b")

def termos_especificos(texto):
    return {t.strip() for t in RE_TERMO.findall(texto) if len(t.strip()) >= 2}

def suspeitos(descricao, pergunta, trecho):
    p, tr = norm(pergunta), norm(trecho)
    return sorted(t for t in termos_especificos(descricao) if norm(t) in p and norm(t) not in tr)

if __name__ == "__main__":
    for linha in open(sys.argv[1]):
        r = json.loads(linha)
        if r["erro"] or r["resposta"]["abstencao"]:
            continue
        fontes = {f["numero"]: f for f in r["resposta"]["fontes"]}
        for l in r["resposta"]["texto"].split("\n"):
            m = re.match(r"\d{2}/\d{2}/\d{4}: (.*?)(?: Resultado da votação:.*| Ato emitido:.*)? \[(\d+)\]$", l)
            if not m:
                continue
            desc, n = m.group(1), int(m.group(2))
            s = suspeitos(desc, r["pergunta"], fontes[n]["trecho"] + " " + fontes[n]["rotulo"])
            if s:
                print(f"P{r['n']} [{n}] DESCARTA por {s} :: {desc[:120]}")
