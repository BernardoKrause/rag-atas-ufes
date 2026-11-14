from app.ingestion.cleaner import _obter_ou_criar_token, TipoEntidade
from app.ingestion.numeros_processo import registrar_numeros
from app.models.documento import NumeroProcesso

SECRET_KEY = b"chave-de-teste"


def test_registra_numero_do_texto_bruto_pelo_hash(db_session):
    token = _obter_ou_criar_token(db_session, SECRET_KEY, TipoEntidade.PROCESSO, "99999.000004/2025-11")

    encontrados, sem_token = registrar_numeros(
        "Processo 99999. 000004/2025- 11 e 99999.000005/2025-11.", SECRET_KEY, db_session
    )

    assert (encontrados, sem_token) == (1, 1)
    assert db_session.get(NumeroProcesso, token).numero == "99999.000004/2025-11"
    assert db_session.query(NumeroProcesso).filter_by(numero="99999.000005/2025-11").count() == 0


def test_registrar_de_novo_nao_duplica(db_session):
    _obter_ou_criar_token(db_session, SECRET_KEY, TipoEntidade.PROCESSO, "99999.000006/2025-11")

    registrar_numeros("99999.000006/2025-11", SECRET_KEY, db_session)
    registrar_numeros("99999.000006/2025-11", SECRET_KEY, db_session)

    assert db_session.query(NumeroProcesso).filter_by(numero="99999.000006/2025-11").count() == 1
