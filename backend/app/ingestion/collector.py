import csv
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

STATUS_PRESENTE = "presente"
LIMITE_PATH_WINDOWS = 260


@dataclass(frozen=True)
class AtaParaProcessar:
    tipo: str
    orgao: str
    numero_reuniao: int | None
    caratere: str
    data_reuniao: date
    arquivo: str
    caminho_pdf: Path


def _path_seguro(caminho: Path) -> Path:
    # alguns nomes de arquivo do corpus ultrapassam o limite classico de 260
    # caracteres do Windows; o prefixo \\?\ pede ao SO pra tratar o caminho
    # como extended-length, sem precisar habilitar long paths globalmente
    texto = str(caminho)
    if (
        sys.platform == "win32"
        and len(texto) >= LIMITE_PATH_WINDOWS
        and not texto.startswith("\\\\?\\")
    ):
        return Path("\\\\?\\" + texto)
    return caminho


def _resolver_pasta_tipo(atas_corpus_path: Path, tipo: str) -> Path:
    candidatos = list(atas_corpus_path.glob(f"{tipo}__*"))
    if len(candidatos) != 1:
        raise FileNotFoundError(
            f"Esperava exatamente uma pasta para o tipo '{tipo}' em {atas_corpus_path}, "
            f"encontrei {len(candidatos)}"
        )
    return candidatos[0]


def coletar_atas(atas_corpus_path: Path) -> list[AtaParaProcessar]:
    csv_path = atas_corpus_path.parent / "inventario_atas.csv"
    atas = []

    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for linha in csv.DictReader(f, delimiter=";"):
            if linha["status"] != STATUS_PRESENTE:
                continue

            pasta_orgao = _resolver_pasta_tipo(atas_corpus_path, linha["tipo"]) / linha["orgao"]
            caminho_pdf = _path_seguro(pasta_orgao / linha["arquivo"])
            if not caminho_pdf.is_file():
                raise FileNotFoundError(f"PDF não encontrado: {caminho_pdf}")

            numero_reuniao = linha["numero_reuniao"]

            atas.append(
                AtaParaProcessar(
                    tipo=linha["tipo"],
                    orgao=linha["orgao"],
                    # CAR e CEFD nao numeram suas atas na fonte; alguns identificadores
                    # (ex.: "extra4") tambem nao sao inteiros simples
                    numero_reuniao=int(numero_reuniao) if numero_reuniao.isdigit() else None,
                    caratere=linha["caratere"],
                    data_reuniao=date.fromisoformat(linha["data"]),
                    arquivo=linha["arquivo"],
                    caminho_pdf=caminho_pdf,
                )
            )

    return atas
