from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.geracao.tipos import Resposta


def registrar_consulta(caminho: Path | None, pergunta: str, configuracao: dict, resposta: Resposta) -> None:
    if caminho is None:
        return
    linha = {
        "data_hora": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pergunta": pergunta,
        "configuracao": configuracao,
        "abstencao": resposta.abstencao,
        "fontes": [fonte.item_id_canonico for fonte in resposta.fontes],
    }
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(linha, ensure_ascii=False) + "\n")
