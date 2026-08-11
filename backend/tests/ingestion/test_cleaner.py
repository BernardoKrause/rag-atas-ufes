from app.ingestion import cleaner
from app.ingestion.cleaner import (
    _obter_ou_criar_token,
    _recortar_sobreposicao_com_processos,
    _subtrair_intervalo,
    anonimizar_texto,
)
from app.models.documento import EntidadeAnonimizada, TipoEntidade

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


def test_numeracao_do_token_incrementa_via_sequence_por_tipo(db_session):
    # _obter_ou_criar_token numera via nextval() de uma sequence do Postgres
    # por tipo (ver migration f4ab1864de74) em vez de COUNT(*)+1 — confirma
    # que a numeracao efetivamente incrementa e que pessoa/processo tem
    # contadores independentes entre si.
    token_pessoa_1 = _obter_ou_criar_token(db_session, SECRET_KEY, TipoEntidade.PESSOA, "Fulano")
    token_pessoa_2 = _obter_ou_criar_token(db_session, SECRET_KEY, TipoEntidade.PESSOA, "Beltrano")
    token_processo_1 = _obter_ou_criar_token(
        db_session, SECRET_KEY, TipoEntidade.PROCESSO, "23068.000001/2025-01"
    )
    token_processo_2 = _obter_ou_criar_token(
        db_session, SECRET_KEY, TipoEntidade.PROCESSO, "23068.000002/2025-01"
    )

    numero_pessoa_1 = int(token_pessoa_1.split("_")[1])
    numero_pessoa_2 = int(token_pessoa_2.split("_")[1])
    numero_processo_1 = int(token_processo_1.split("_")[1])
    numero_processo_2 = int(token_processo_2.split("_")[1])

    assert token_pessoa_1.startswith("PESSOA_")
    assert token_processo_1.startswith("PROCESSO_")
    assert numero_pessoa_2 == numero_pessoa_1 + 1
    # sequences sao independentes por tipo: a de processo incrementa por
    # conta propria, nao acompanha quantas pessoas ja foram numeradas
    assert numero_processo_2 == numero_processo_1 + 1


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


def test_subtrair_intervalo_sem_sobreposicao_mantem_o_alvo():
    assert _subtrair_intervalo((0, 5), (10, 15)) == [(0, 5)]
    assert _subtrair_intervalo((10, 15), (0, 5)) == [(10, 15)]


def test_subtrair_intervalo_remove_sobreposicao_no_fim():
    assert _subtrair_intervalo((0, 10), (6, 15)) == [(0, 6)]


def test_subtrair_intervalo_remove_sobreposicao_no_comeco():
    assert _subtrair_intervalo((6, 15), (0, 10)) == [(10, 15)]


def test_subtrair_intervalo_remove_alvo_totalmente_contido():
    assert _subtrair_intervalo((5, 8), (0, 10)) == []


def test_subtrair_intervalo_alvo_contem_intervalo_removido_gera_dois_pedacos():
    assert _subtrair_intervalo((0, 10), (4, 6)) == [(0, 4), (6, 10)]


def test_recortar_sobreposicao_com_processos_preserva_pessoa_sem_conflito():
    pessoas = [(0, 10)]
    processos = [(20, 30)]
    assert _recortar_sobreposicao_com_processos(pessoas, processos) == pessoas


def test_recortar_sobreposicao_com_processos_recorta_pessoa_grudada_no_numero():
    # simula "Silva23068.001234/2025-11": o NER errou o limite e incluiu
    # os primeiros digitos do numero de processo dentro do span de PESSOA
    pessoas = [(0, 20)]
    processos = [(15, 40)]
    assert _recortar_sobreposicao_com_processos(pessoas, processos) == [(0, 15)]


def test_anonimizar_texto_nao_corrompe_saida_quando_ner_se_sobrepoe_ao_processo(
    db_session, monkeypatch
):
    # reproduz o bug do achado #1: um span de PESSOA que invade o span do
    # PROCESSO nao pode corromper a substituicao feita de tras pra frente.
    texto = "Assinado por Silva23068.001234/2025-11 em anexo."
    inicio_processo = texto.index("23068.001234/2025-11")
    inicio_pessoa = texto.index("Silva")
    fim_pessoa_com_erro_de_limite = inicio_processo + 5  # invade o numero

    monkeypatch.setattr(
        cleaner,
        "_achar_entidades_pessoa",
        lambda _texto: [(inicio_pessoa, fim_pessoa_com_erro_de_limite)],
    )

    resultado = anonimizar_texto(texto, SECRET_KEY, db_session)

    assert "23068.001234/2025-11" not in resultado
    assert "Silva" not in resultado
    assert resultado.startswith("Assinado por PESSOA_")
    assert resultado.endswith(" em anexo.")
    assert "PROCESSO_" in resultado


def test_texto_maior_que_uma_janela_de_ner_ainda_anonimiza_o_final(db_session):
    # forca a passagem por >1 janela (LARGURA_JANELA_NER = 1500 caracteres) e
    # confirma que uma pessoa citada perto do fim do texto nao fica de fora
    enchimento = "Este parágrafo é apenas texto de preenchimento sem entidades. " * 40
    texto = enchimento + "Ao final, falou o professor João da Silva Souza."

    resultado = anonimizar_texto(texto, SECRET_KEY, db_session)

    assert "João da Silva Souza" not in resultado
    assert "PESSOA_" in resultado
