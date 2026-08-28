from __future__ import annotations

from neo4j import Driver, GraphDatabase

from app.core.config import settings


def obter_driver() -> Driver:
    return GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value())
    )


def executar_escrita(driver: Driver, query: str, **params) -> None:
    with driver.session() as sessao:
        sessao.run(query, **params)


def executar_leitura(driver: Driver, query: str, **params) -> list[dict]:
    with driver.session() as sessao:
        return [dict(registro) for registro in sessao.run(query, **params)]
