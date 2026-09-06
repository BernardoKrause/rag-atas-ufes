import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


@pytest.fixture()
def db_session():
    """Sessao contra o Postgres real, dentro de uma transacao externa que e
    sempre revertida ao final do teste — nao deixa residuo entre testes nem
    exige limpeza manual de tabela.

    Usa um SAVEPOINT (nao a transacao externa em si) como alvo de
    commit()/rollback() do codigo sob teste: sem isso, um commit() dentro do
    codigo sob teste (ex.: pipeline.py fazendo commit por ata) encerraria a
    transacao externa de verdade, gravando dado permanente no Postgres em vez
    de ficar restrito ao teste. O listener recria o SAVEPOINT sempre que o
    anterior termina, pra commits/rollbacks subsequentes no mesmo teste
    continuarem funcionando.
    """
    engine = create_engine(settings.database_url)
    conexao = engine.connect()
    transacao = conexao.begin()
    sessao = sessionmaker(bind=conexao)()
    savepoint = conexao.begin_nested()

    @event.listens_for(sessao, "after_transaction_end")
    def _reiniciar_savepoint(sessao_evento, transacao_encerrada):
        nonlocal savepoint
        if not savepoint.is_active:
            savepoint = conexao.begin_nested()

    yield sessao

    sessao.close()
    transacao.rollback()
    conexao.close()
    engine.dispose()


@pytest.fixture()
def qdrant_cliente():
    from app.ingestion.indexador import garantir_collection, obter_cliente_qdrant

    cliente = obter_cliente_qdrant()
    garantir_collection(cliente)
    yield cliente
    cliente.close()
