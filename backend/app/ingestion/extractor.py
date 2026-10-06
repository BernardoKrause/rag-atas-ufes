import logging
import re
from pathlib import Path

import fitz

from app.ingestion._extenso import NUM_10_19, NUM_DEZENA, NUM_UNIDADE, ZERO, parse_cardinal, tokenizar

logger = logging.getLogger(__name__)

RE_HORA_COMPACTA = re.compile(r"(\d{1,2})[Hh](\d{2})")
RE_HORA_HHMM = re.compile(r"(\d{1,2}):(\d{2})")

JANELA_ABERTURA = 3000

PALAVRAS_HORA = set(NUM_UNIDADE) | set(NUM_10_19) | set(NUM_DEZENA) | set(ZERO)

# cada centro do corpus fica em exatamente um campus fisico da UFES — nao ha
# necessidade (nem confiabilidade) em tentar re-descobrir isso fazendo regex
# no texto da ata, que so cita o campus explicitamente em alguns modelos
CENTRO_CAMPUS = {
    "CAR": "Goiabeiras",
    "CCE": "Goiabeiras",
    "CCHN": "Goiabeiras",
    "CE": "Goiabeiras",
    "CEFD": "Goiabeiras",
    "CT": "Goiabeiras",
    "CCAE": "Alegre",
    "CCENS": "Alegre",
    "CEUNES": "São Mateus",
    "CCS": "Maruípe",
}


def mapear_campus(centro: str) -> str:
    try:
        return CENTRO_CAMPUS[centro]
    except KeyError:
        raise ValueError(f"centro sem campus mapeado: {centro}") from None


def _corrigir_ligadura_ti_quebrada(texto: str) -> str:
    return texto.replace("Ɵ", "ti")


def _normalizar_espacos(texto: str) -> str:
    # alguns modelos de ata (ex.: CT/CEUNES) tem cada palavra separada por
    # "\n" + varios espacos — colapsa tudo pra um espaco simples antes de
    # qualquer checagem de substring literal com mais de uma palavra
    return re.sub(r"\s+", " ", texto)


def _janela_abertura_normalizada(texto: str) -> str:
    return _normalizar_espacos(texto[:JANELA_ABERTURA].upper())


RE_NUMERACAO_MARGEM = re.compile(r"(?m)^[ \t]*\d{1,3}[ \t]*$\n?")


def _neutralizar_numeracao_de_margem(texto: str) -> str:
    candidatos = list(RE_NUMERACAO_MARGEM.finditer(texto))
    if len(candidatos) < 2:
        return texto
    for match in reversed(candidatos):
        texto = texto[:match.start()] + " " * len(match.group(0)) + texto[match.end():]
    return texto


RE_CONTADOR_PAGINA = re.compile(r"^.*\d{1,4}(?:\s*/\s*\d{1,4})?\s*\.?\s*$")

LIMIAR_CABECALHO_CHARS = 8


def _linha(pagina: str, indice: int) -> str | None:
    linhas = pagina.split("\n")
    fora_do_range = indice >= len(linhas) if indice >= 0 else -indice > len(linhas)
    return None if fora_do_range else linhas[indice]


def _contagem_de_linhas_repetidas(paginas: list[str], inicio: int, passo: int) -> int:
    indice = inicio
    confirmadas = 0
    pendente_contador = False
    while True:
        linhas = [_linha(p, indice) for p in paginas]
        if any(linha is None for linha in linhas):
            break
        if all(linha == linhas[0] for linha in linhas):
            confirmadas = abs(indice - inicio) + 1
            indice += passo
            pendente_contador = False
            continue
        if not pendente_contador and all(RE_CONTADOR_PAGINA.match(linha) for linha in linhas):
            pendente_contador = True
            indice += passo
            continue
        break
    return confirmadas


def _sem_linhas_em_branco_no_topo(pagina: str) -> str:
    linhas = pagina.split("\n")
    indice = 0
    while indice < len(linhas) and not linhas[indice].strip():
        indice += 1
    return "\n".join(linhas[indice:])


def _remover_cabecalho_e_rodape_repetidos(paginas_texto: list[str]) -> list[str]:
    if len(paginas_texto) < 2:
        return paginas_texto

    n_rodape = _contagem_de_linhas_repetidas(paginas_texto, -1, -1)
    sem_rodape = [
        "\n".join(pagina.split("\n")[: len(pagina.split("\n")) - n_rodape])
        for pagina in paginas_texto
    ] if n_rodape else paginas_texto

    sem_linha_em_branco_no_topo = [_sem_linhas_em_branco_no_topo(p) for p in sem_rodape]

    grupo_cabecalho = (
        sem_linha_em_branco_no_topo[1:] if len(sem_linha_em_branco_no_topo) >= 3
        else sem_linha_em_branco_no_topo
    )
    n_cabecalho = _contagem_de_linhas_repetidas(grupo_cabecalho, 0, 1)
    primeiras_linhas = grupo_cabecalho[0].split("\n")[:n_cabecalho]
    conteudo_nao_branco = "".join(linha.strip() for linha in primeiras_linhas)
    if not n_cabecalho or len(conteudo_nao_branco) < LIMIAR_CABECALHO_CHARS:
        return sem_rodape

    novas_paginas = [sem_rodape[0]]
    for pagina in sem_linha_em_branco_no_topo[1:]:
        linhas = pagina.split("\n")
        novas_paginas.append("\n".join(linhas[n_cabecalho:]))
    return novas_paginas


def extrair_texto_bruto(caminho_pdf: Path) -> tuple[str, list[int]]:
    """Retorna o texto completo e, junto, o offset (indice no texto) onde
    cada pagina comeca — necessario pro segmentador (Parte 3) saber em que
    pagina do PDF cada item de pauta cai."""
    fitz.TOOLS.mupdf_display_errors(False)
    try:
        doc = fitz.open(caminho_pdf)
        try:
            paginas_texto = [_corrigir_ligadura_ti_quebrada(pagina.get_text()) for pagina in doc]
        finally:
            doc.close()
    finally:
        aviso = fitz.TOOLS.mupdf_warnings()
        fitz.TOOLS.mupdf_display_errors(True)

    if aviso:
        logger.warning("MuPDF emitiu aviso ao extrair %s: %s", caminho_pdf, aviso)

    paginas_texto = _remover_cabecalho_e_rodape_repetidos(paginas_texto)
    paginas_texto = [_neutralizar_numeracao_de_margem(p) for p in paginas_texto]

    offsets = []
    offset_atual = 0
    for texto_pagina in paginas_texto:
        offsets.append(offset_atual)
        offset_atual += len(texto_pagina) + 1  # +1 pelo separador "\n" do join

    return "\n".join(paginas_texto), offsets


def extrair_metadados_organizacionais(tipo: str, orgao: str) -> dict[str, str | None]:
    """Deriva os metadados a partir dos codigos do inventario, nao do PDF."""
    tipo_orgao = tipo.split("_")[-1]
    partes = orgao.split("_")

    if tipo_orgao == "A":
        centro = partes[0]
        departamento = "_".join(partes[1:]) or None
        return {"centro": centro, "campus": mapear_campus(centro), "tipo_orgao": tipo_orgao, "departamento": departamento, "curso": None, "area_tematica": None}
    if tipo_orgao == "B":
        return {"centro": orgao, "campus": mapear_campus(orgao), "tipo_orgao": tipo_orgao, "departamento": None, "curso": None, "area_tematica": None}
    if tipo_orgao == "C":
        # "{CENTRO}_CamaraLocal_{AREA}"
        centro = partes[0]
        area = "_".join(partes[2:]) or None
        return {"centro": centro, "campus": mapear_campus(centro), "tipo_orgao": tipo_orgao, "departamento": None, "curso": None, "area_tematica": area}
    if tipo_orgao == "D":
        # "{CENTRO}_Colegiado_{CURSO}"
        centro = partes[0]
        curso = "_".join(partes[2:]) or None
        return {"centro": centro, "campus": mapear_campus(centro), "tipo_orgao": tipo_orgao, "departamento": None, "curso": curso, "area_tematica": None}

    raise ValueError(f"tipo_orgao desconhecido: {tipo_orgao}")


def _achar_inicio_numero(tokens: list[str], indice_ultimo_token: int) -> int:
    """Retorna o indice de inicio, cobrindo o caso composto "DEZENA E UNIDADE"
    (ex.: "VINTE E DOIS")."""
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
        if tok == "MINUTOS" and idx >= 1 and tokens[idx - 1] in PALAVRAS_HORA:
            inicio_minuto = _achar_inicio_numero(tokens, idx - 1)
            if inicio_minuto < 1 or tokens[inicio_minuto - 1] != "E":
                continue
            minuto, _ = parse_cardinal(tokens, inicio_minuto)
            j = inicio_minuto - 2
            if j >= 0 and tokens[j] == "HORAS":
                j -= 1
            if j < 0 or minuto is None:
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


_RE_MODALIDADE_VIDEO = re.compile(r"WEBCONFER|VIDEOCONFER|GOOGLE MEET|MEET\.GOOGLE\.COM")
_RE_MODALIDADE_PRESENCIAL = re.compile(r"SALA DE REUNI")


def extrair_modalidade(texto: str) -> str | None:
    janela = _janela_abertura_normalizada(texto)

    # cada modalidade concorre pelo seu ULTIMO indicio no texto — cobre o caso
    # em que a ata primeiro descarta uma modalidade ("impossibilidade de
    # webconferencia") e so depois relata a que de fato ocorreu
    candidatos: list[tuple[int, str]] = []

    fins = [m.end() for m in _RE_MODALIDADE_VIDEO.finditer(janela)]
    if fins:
        candidatos.append((max(fins), "Videoconferência"))

    if "CONSULTA ELETR" in janela or ("CONSULTA" in janela and "E-MAIL" in janela):
        fins = [m.end() for m in re.finditer("CONSULTA|E-MAIL", janela)]
        candidatos.append((max(fins), "Consulta eletrônica"))

    fins = [m.end() for m in _RE_MODALIDADE_PRESENCIAL.finditer(janela)]
    if fins:
        candidatos.append((max(fins), "Presencial"))

    if not candidatos:
        return None
    return max(candidatos, key=lambda c: c[0])[1]


def extrair_local(texto: str) -> str | None:
    janela = texto[:JANELA_ABERTURA]

    m = re.search(r"https?://\S+", janela)
    if m:
        return m.group(0).rstrip(".,;)]}")

    m = re.search(r"N[AO]\s+(SALA[^,.]*)", janela, re.IGNORECASE)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip().title()

    return None


_RE_QUORUM_NEGATIVO = re.compile(r"N[ÃA]O\s+(HOUVE|H[ÁA]|HAVENDO)\s+QU[ÓO]RUM|SEM QUÓRUM")
_RE_QUORUM_POSITIVO = re.compile(r"HAVENDO QU|MERO LEGAL DE MEMBROS")


def extrair_quorum_declarado(texto: str) -> bool | None:
    janela = _janela_abertura_normalizada(texto)

    # concorre pelo ULTIMO indicio de cada lado — cobre o caso em que a ata
    # relata a falta de quorum na 1a chamada e o quorum atingido na 2a
    fins_negativo = [m.end() for m in _RE_QUORUM_NEGATIVO.finditer(janela)]
    fins_positivo = [m.end() for m in _RE_QUORUM_POSITIVO.finditer(janela)]

    if not fins_negativo and not fins_positivo:
        return None
    if not fins_negativo:
        return True
    if not fins_positivo:
        return False
    return max(fins_positivo) > max(fins_negativo)


_RE_STATUS_EM_APROVACAO = re.compile(r"ATA EM APROVA[ÇC][ÃA]O")


def extrair_marca_dagua_em_aprovacao(texto: str) -> bool:
    janela = _janela_abertura_normalizada(texto)
    return bool(_RE_STATUS_EM_APROVACAO.search(janela))


def extrair_campos(tipo: str, orgao: str, caminho_pdf: Path) -> dict:
    """quantidade_presentes, quantidade_ausentes e departamentos_representados
    ficam de fora de proposito: dependem de reconhecer nomes de pessoas de
    forma confiavel, o que e trabalho do NER do cleaner.py (proximo
    fragmento) — nao faz sentido duplicar essa logica aqui com regex fragil.
    """
    texto_bruto, paginas_offsets = extrair_texto_bruto(caminho_pdf)
    metadados = extrair_metadados_organizacionais(tipo, orgao)

    return {
        **metadados,
        "texto_bruto": texto_bruto,
        "paginas_offsets": paginas_offsets,
        "horario_inicio": extrair_horario_inicio(texto_bruto),
        "modalidade": extrair_modalidade(texto_bruto),
        "quorum_declarado": extrair_quorum_declarado(texto_bruto),
        "em_aprovacao": extrair_marca_dagua_em_aprovacao(texto_bruto),
    }
