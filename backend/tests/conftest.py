import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


@pytest.fixture()
def db_session():
    """Sessao contra o Postgres real, dentro de uma transacao que e sempre
    revertida ao final do teste — nao deixa residuo entre testes nem exige
    limpeza manual de tabela."""
    engine = create_engine(settings.database_url)
    conexao = engine.connect()
    transacao = conexao.begin()
    sessao = sessionmaker(bind=conexao)()

    yield sessao

    sessao.close()
    transacao.rollback()
    conexao.close()
    engine.dispose()
