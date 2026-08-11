import pytest
from sqlalchemy.exc import IntegrityError

from app.models.documento import EntidadeAnonimizada


def test_hash_entidade_duplicado_viola_constraint(db_session):
    db_session.add(
        EntidadeAnonimizada(hash_entidade="a" * 64, tipo="pessoa", token="PESSOA_0001")
    )
    db_session.flush()

    db_session.add(
        EntidadeAnonimizada(hash_entidade="a" * 64, tipo="pessoa", token="PESSOA_0002")
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_tipo_e_token_duplicados_para_hash_diferente_viola_constraint(db_session):
    # cobre o achado de code review: _obter_ou_criar_token calcula o numero do
    # token com um COUNT(*)+1 nao atomico — duas execucoes concorrentes do
    # pipeline apontando pro mesmo banco podem calcular o mesmo numero pra
    # entidades diferentes. Essa constraint nao evita a corrida, mas garante
    # que o segundo INSERT falhe alto (IntegrityError) em vez de gravar duas
    # pessoas/processos reais diferentes sob o mesmo token silenciosamente.
    db_session.add(
        EntidadeAnonimizada(hash_entidade="b" * 64, tipo="pessoa", token="PESSOA_0001")
    )
    db_session.flush()

    db_session.add(
        EntidadeAnonimizada(hash_entidade="c" * 64, tipo="pessoa", token="PESSOA_0001")
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_mesmo_token_em_tipos_diferentes_nao_viola_constraint(db_session):
    db_session.add(
        EntidadeAnonimizada(hash_entidade="d" * 64, tipo="pessoa", token="0001")
    )
    db_session.add(
        EntidadeAnonimizada(hash_entidade="e" * 64, tipo="processo", token="0001")
    )
    db_session.flush()
