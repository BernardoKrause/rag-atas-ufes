from app.ingestion.cleaner import anonimizar_texto
from app.models.documento import EntidadeAnonimizada

SECRET_KEY = b"chave-de-teste-nao-usar-em-producao"
OUTRA_SECRET_KEY = b"outra-chave-de-teste"

TEXTO_ABERTURA = (
    "Presente o professor João da Silva Souza, representante do Departamento, "
    "e a Sra. Maria Oliveira, secretária. O processo 23068.001234/2025-11 foi "
    "aprovado por unanimidade."
)


def test_pessoas_e_processo_sao_substituidos_por_token(db_session):
    resultado = anonimizar_texto(TEXTO_ABERTURA, SECRET_KEY, db_session)

    assert "João da Silva Souza" not in resultado
    assert "Maria Oliveira" not in resultado
    assert "23068.001234/2025-11" not in resultado
    assert "PESSOA_" in resultado
    assert "PROCESSO_" in resultado


def test_mesma_pessoa_gera_sempre_o_mesmo_token_em_atas_diferentes(db_session):
    ata_1 = "O professor João da Silva Souza apresentou o relatório."
    ata_2 = "Segundo o professor João da Silva Souza, o prazo está mantido."

    resultado_1 = anonimizar_texto(ata_1, SECRET_KEY, db_session)
    resultado_2 = anonimizar_texto(ata_2, SECRET_KEY, db_session)

    token_1 = resultado_1.split("O professor ")[1].split(" apresentou")[0]
    token_2 = resultado_2.split("Segundo o professor ")[1].split(", o prazo")[0]
    assert token_1 == token_2


def test_reprocessar_o_mesmo_texto_e_idempotente(db_session):
    primeira_vez = anonimizar_texto(TEXTO_ABERTURA, SECRET_KEY, db_session)
    segunda_vez = anonimizar_texto(TEXTO_ABERTURA, SECRET_KEY, db_session)

    assert primeira_vez == segunda_vez


def test_pessoas_diferentes_geram_tokens_diferentes(db_session):
    anonimizar_texto(TEXTO_ABERTURA, SECRET_KEY, db_session)

    entidades = db_session.query(EntidadeAnonimizada).filter_by(tipo="pessoa").all()
    tokens = {e.token for e in entidades}
    assert len(entidades) == 2
    assert len(tokens) == 2


def test_chave_secreta_diferente_gera_token_diferente_para_mesma_pessoa(db_session):
    texto = "O professor João da Silva Souza apresentou o relatório."

    resultado_a = anonimizar_texto(texto, SECRET_KEY, db_session)
    resultado_b = anonimizar_texto(texto, OUTRA_SECRET_KEY, db_session)

    token_a = resultado_a.split("O professor ")[1].split(" apresentou")[0]
    token_b = resultado_b.split("O professor ")[1].split(" apresentou")[0]
    assert token_a != token_b


def test_mesmo_numero_de_processo_gera_sempre_o_mesmo_token(db_session):
    texto = "O processo 23068.001234/2025-11 foi distribuído para relatoria."

    resultado_1 = anonimizar_texto(texto, SECRET_KEY, db_session)
    resultado_2 = anonimizar_texto(texto, SECRET_KEY, db_session)

    assert resultado_1 == resultado_2
    entidades = db_session.query(EntidadeAnonimizada).filter_by(tipo="processo").all()
    assert len(entidades) == 1


def test_texto_sem_pessoas_ou_processos_fica_inalterado(db_session):
    texto = "Ata da reunião ordinária, sem menção a quórum."
    assert anonimizar_texto(texto, SECRET_KEY, db_session) == texto


def test_texto_maior_que_uma_janela_de_ner_ainda_anonimiza_o_final(db_session):
    # forca a passagem por >1 janela (LARGURA_JANELA_NER = 1500 caracteres) e
    # confirma que uma pessoa citada perto do fim do texto nao fica de fora
    enchimento = "Este parágrafo é apenas texto de preenchimento sem entidades. " * 40
    texto = enchimento + "Ao final, falou o professor João da Silva Souza."

    resultado = anonimizar_texto(texto, SECRET_KEY, db_session)

    assert "João da Silva Souza" not in resultado
    assert "PESSOA_" in resultado
