from __future__ import annotations

from dataclasses import dataclass

TAMANHO_MAX_FRAGMENTO = 3000
SOBREPOSICAO_FRAGMENTO = 300

SECAO_APROVACAO_ATA = "APROVAÇÃO DE ATA"
SECAO_COMUNICACOES = "COMUNICAÇÕES"
SECAO_EXPEDIENTE = "EXPEDIENTE"
SECAO_EXCLUSAO_DE_PAUTA = "EXCLUSÃO DE PAUTA"
SECAO_ORDEM_DO_DIA = "ORDEM DO DIA"
SECAO_PAUTA = "PAUTA"
SECAO_INFORMES = "INFORMES"
SECAO_PALAVRA_LIVRE = "PALAVRA LIVRE"
SECAO_PROCESSOS_PROJETOS = "PROCESSOS/PROJETOS"


@dataclass(frozen=True)
class ItemDetectado:
    secao: str
    numero_item: str
    inicio: int  # offset no texto normalizado
    fim: int  # offset no texto normalizado
    texto: str


def _normalizar_com_mapa(texto: str) -> tuple[str, list[int]]:
    """Colapsa qualquer sequencia de espaco em branco (incluindo quebras de
    linha — alguns modelos de ata, ex. CT, tem uma palavra por linha) num
    unico espaco, preservando um mapa de cada indice do texto normalizado
    pro indice correspondente no texto original. Necessario pro segmentador
    continuar sabendo em que pagina do PDF cada item cai depois de
    normalizar — normalizar sem preservar o mapa perderia essa
    correspondencia."""
    partes: list[str] = []
    mapa: list[int] = []
    em_espaco = False
    for i, ch in enumerate(texto):
        if ch.isspace():
            em_espaco = True
            continue
        if em_espaco:
            if partes:
                partes.append(" ")
                mapa.append(i)
            em_espaco = False
        partes.append(ch)
        mapa.append(i)
    return "".join(partes), mapa
