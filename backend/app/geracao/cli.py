from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.geracao.llm import criar_cliente_llm
from app.geracao.respondedor import responder
from app.geracao.tipos import ErroGeracao
from app.grafo.cliente import obter_driver
from app.ingestion.indexador import _obter_cliente_qdrant


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Responde uma pergunta sobre as atas da UFES.")
    parser.add_argument("pergunta")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    Sessao = sessionmaker(bind=create_engine(settings.database_url))
    cliente_qdrant = _obter_cliente_qdrant()
    driver = obter_driver()
    try:
        with Sessao() as sessao:
            resposta = responder(
                args.pergunta, sessao, cliente_qdrant, driver, criar_cliente_llm()
            )
    except ErroGeracao as erro:
        print(f"Erro na geração: {erro}", file=sys.stderr)
        return 1
    finally:
        driver.close()
        cliente_qdrant.close()

    print(resposta.texto)
    if resposta.fontes:
        print("\nFontes:")
        for fonte in resposta.fontes:
            print(f"[{fonte.numero}] {fonte.rotulo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
