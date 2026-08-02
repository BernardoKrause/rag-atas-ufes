import re
from pathlib import Path

import fitz

from app.ingestion._extenso import NUM_10_19, NUM_DEZENA, NUM_UNIDADE, ZERO, parse_cardinal, tokenizar

RE_HORA_COMPACTA = re.compile(r"(\d{1,2})[Hh](\d{2})")
RE_HORA_HHMM = re.compile(r"(\d{1,2}):(\d{2})")

JANELA_ABERTURA = 3000

PALAVRAS_HORA = set(NUM_UNIDADE) | set(NUM_10_19) | set(NUM_DEZENA) | set(ZERO)

# cada centro do corpus fica em exatamente um campus fisico da UFES — nao ha
# necessidade (nem confiabilidade) em tentar re-descobrir isso fazendo regex
# no texto da ata, que so cita o campus explicitamente em alguns modelos
CENTRO_CAMPUS = {
    "CAR": "Goiabeiras",
    "CCHN": "Goiabeiras",
    "CE": "Goiabeiras",
    "CEFD": "Goiabeiras",
    "CT": "Goiabeiras",
    "CCAE": "Alegre",
    "CCENS": "São Mateus",
    "CEUNES": "São Mateus",
}


def mapear_campus(centro: str) -> str:
    try:
        return CENTRO_CAMPUS[centro]
    except KeyError:
        raise ValueError(f"centro sem campus mapeado: {centro}") from None


def _normalizar_espacos(texto: str) -> str:
    # alguns modelos de ata (ex.: CT/CEUNES) tem cada palavra separada por
    # "\n" + varios espacos — colapsa tudo pra um espaco simples antes de
    # qualquer checagem de substring literal com mais de uma palavra
    return re.sub(r"\s+", " ", texto)


def extrair_texto_bruto(caminho_pdf: Path) -> str:
    doc = fitz.open(caminho_pdf)
    try:
        return "\n".join(pagina.get_text() for pagina in doc)
    finally:
        doc.close()


def extrair_metadados_organizacionais(tipo: str, orgao: str) -> dict[str, str | None]:
    """Deriva centro/tipo_orgao/departamento/curso/area_tematica dos codigos ja
    curados no inventario (nao depende de parsing do PDF)."""
    tipo_orgao = tipo.split("_")[-1]
    partes = orgao.split("_")

    if tipo_orgao == "A":
        centro = partes[0]
        return {"centro": centro, "campus": mapear_campus(centro), "tipo_orgao": tipo_orgao, "departamento": "_".join(partes[1:]), "curso": None, "area_tematica": None}
    if tipo_orgao == "B":
        return {"centro": orgao, "campus": mapear_campus(orgao), "tipo_orgao": tipo_orgao, "departamento": None, "curso": None, "area_tematica": None}
    if tipo_orgao == "C":
        # "{CENTRO}_CamaraLocal_{AREA}"
        centro = partes[0]
        area = partes[2] if len(partes) > 2 else None
        return {"centro": centro, "campus": mapear_campus(centro), "tipo_orgao": tipo_orgao, "departamento": None, "curso": None, "area_tematica": area}
    if tipo_orgao == "D":
        # "{CENTRO}_Colegiado_{CURSO}"
        centro = partes[0]
        curso = partes[2] if len(partes) > 2 else None
        return {"centro": centro, "campus": mapear_campus(centro), "tipo_orgao": tipo_orgao, "departamento": None, "curso": curso, "area_tematica": None}

    raise ValueError(f"tipo_orgao desconhecido: {tipo_orgao}")


def _achar_inicio_numero(tokens: list[str], indice_ultimo_token: int) -> int:
    """Dado o indice do ULTIMO token de um numeral cardinal, retorna o indice de
    inicio (cobre o caso composto "DEZENA E UNIDADE", ex.: "VINTE E DOIS")."""
    if (
        indice_ultimo_token >= 2
        and tokens[indice_ultimo_token] in NUM_UNIDADE
        and tokens[indice_ultimo_token - 1] == "E"
        and tokens[indice_ultimo_token - 2] in NUM_DEZENA
    ):
        return indice_ultimo_token - 2
    return indice_ultimo_token


def extrair_horario_inicio(texto: str) -> str | None:
    janela = texto[:JANELA_ABERTURA]

    m = RE_HORA_COMPACTA.search(janela)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    m = RE_HORA_HHMM.search(janela)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"

    tokens = tokenizar(janela)

    # 1a passada: padrao "<hora> [HORAS] E <minuto> MINUTOS" (mais especifico,
    # tem prioridade sobre um "HORAS" isolado que apareça antes na mesma frase,
    # ex.: "TREZE HORAS E TRINTA MINUTOS" nao pode parar em "TREZE HORAS")
    for idx, tok in enumerate(tokens):
        if tok == "MINUTOS" and idx >= 3 and tokens[idx - 1] in PALAVRAS_HORA and tokens[idx - 2] == "E":
            minuto, _ = parse_cardinal(tokens, idx - 1)
            j = idx - 3
            if j >= 0 and tokens[j] == "HORAS":
                j -= 1
            if j < 0:
                continue
            inicio_hora = _achar_inicio_numero(tokens, j)
            hora, _ = parse_cardinal(tokens, inicio_hora)
            if hora is not None and minuto is not None:
                return f"{hora:02d}:{minuto:02d}"

    # 2a passada: "HORAS" isolado (sem minutos)
    for idx, tok in enumerate(tokens):
        if tok == "HORAS" and idx >= 1:
            inicio_hora = _achar_inicio_numero(tokens, idx - 1)
            hora, prox = parse_cardinal(tokens, inicio_hora)
            if hora is not None and prox == idx:
                return f"{hora:02d}:00"

    return None


def extrair_modalidade(texto: str) -> str | None:
    janela = _normalizar_espacos(texto[:JANELA_ABERTURA].upper())
    if (
        "WEBCONFER" in janela
        or "VIDEOCONFER" in janela
        or "GOOGLE MEET" in janela
        or "MEET.GOOGLE.COM" in janela
    ):
        return "Videoconferência"
    if "CONSULTA ELETR" in janela or ("CONSULTA" in janela and "E-MAIL" in janela):
        return "Consulta eletrônica"
    if "SALA DE REUNI" in janela:
        return "Presencial"
    return None


def extrair_local(texto: str) -> str | None:
    janela = texto[:JANELA_ABERTURA]

    m = re.search(r"https?://\S+", janela)
    if m:
        return m.group(0).rstrip(".,;")

    m = re.search(r"N[AO]\s+(SALA[^,.]*)", janela, re.DOTALL | re.IGNORECASE)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip().title()

    return None


def extrair_quorum_declarado(texto: str) -> bool | None:
    janela = _normalizar_espacos(texto[:JANELA_ABERTURA].upper())
    if (
        re.search(r"N[ÃA]O\s+(HOUVE|H[ÁA]|HAVENDO)\s+QU[ÓO]RUM", janela)
        or "SEM QU" + chr(0xD3) + "RUM" in janela
    ):
        return False
    if "HAVENDO QU" in janela or "MERO LEGAL DE MEMBROS" in janela:
        return True
    return None


def extrair_campos(tipo: str, orgao: str, caminho_pdf: Path) -> dict:
    """Extrai texto bruto + todos os campos canonicos de uma ata.

    quantidade_presentes, quantidade_ausentes e departamentos_representados
    ficam de fora de proposito: dependem de reconhecer nomes de pessoas de
    forma confiavel, o que e trabalho do NER do cleaner.py (proximo
    fragmento) — nao faz sentido duplicar essa logica aqui com regex fragil.
    """
    texto_bruto = extrair_texto_bruto(caminho_pdf)
    metadados = extrair_metadados_organizacionais(tipo, orgao)

    return {
        **metadados,
        "texto_bruto": texto_bruto,
        "horario_inicio": extrair_horario_inicio(texto_bruto),
        "modalidade": extrair_modalidade(texto_bruto),
        "local": extrair_local(texto_bruto),
        "quorum_declarado": extrair_quorum_declarado(texto_bruto),
    }
