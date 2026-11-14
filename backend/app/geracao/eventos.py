from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date

RE_MARCADOR = re.compile(r"\s*\[\s*\d+(?:\s*,\s*\d+)*\s*\]")


@dataclass(frozen=True)
class Evento:
    evidencia: int
    descricao: str


def _numero(valor) -> int | None:
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, str) and valor.strip().isdigit():
        return int(valor.strip())
    return None


def _registros(saida: str) -> list | None:
    decodificador = json.JSONDecoder()
    registros, achou, posicao = [], False, saida.find("{")
    while posicao != -1:
        try:
            objeto, fim = decodificador.raw_decode(saida, posicao)
        except json.JSONDecodeError:
            posicao = saida.find("{", posicao + 1)
            continue
        if isinstance(objeto, dict) and isinstance(objeto.get("eventos"), list):
            registros.extend(objeto["eventos"])
            achou = True
        posicao = saida.find("{", fim)
    return registros if achou else None


def interpretar_eventos(saida: str, datas: dict[int, date]) -> list[Evento] | None:
    registros = _registros(saida)
    if registros is None:
        return None

    eventos = []
    for registro in registros:
        if not isinstance(registro, dict) or registro.get("relevante") is not True:
            continue
        numero = _numero(registro.get("evidencia"))
        descricao = _limpar(registro.get("descricao"))
        if numero in datas and descricao:
            eventos.append(Evento(numero, descricao))
    return sorted(eventos, key=lambda evento: datas[evento.evidencia])


def _limpar(valor) -> str:
    return RE_MARCADOR.sub("", str(valor or "")).strip()


def ler_resposta_direta(saida: str) -> str:
    inicio = saida.find("{")
    if inicio == -1:
        return ""
    try:
        objeto, _ = json.JSONDecoder().raw_decode(saida, inicio)
    except json.JSONDecodeError:
        return ""
    resposta = objeto.get("resposta") if isinstance(objeto, dict) else None
    return _limpar(resposta) if isinstance(resposta, str) else ""


def montar_texto(eventos: list[Evento], datas: dict[int, date], resposta_direta: str = "") -> str:
    linhas = "\n".join(
        f"{datas[e.evidencia].strftime('%d/%m/%Y')}: {e.descricao} [{e.evidencia}]" for e in eventos
    )
    return f"{resposta_direta}\n\n{linhas}" if resposta_direta else linhas
