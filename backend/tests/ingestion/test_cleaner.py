import re

from app.ingestion import cleaner
from app.ingestion.cleaner import (
    _obter_ou_criar_token,
    _recortar_sobreposicao,
    _subtrair_intervalo,
    anonimizar_texto,
    remapear_offsets,
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
    resultado, _ = anonimizar_texto(TEXTO_ABERTURA, SECRET_KEY, db_session)

    assert "João da Silva Souza" not in resultado
    assert "Maria Oliveira" not in resultado
    assert "23068.001234/2025-11" not in resultado
    assert "PESSOA_" in resultado
    assert "PROCESSO_" in resultado


def test_mesma_pessoa_gera_sempre_o_mesmo_token_em_atas_diferentes(db_session):
    ata_1 = "O professor João da Silva Souza apresentou o relatório."
    ata_2 = "Segundo o professor João da Silva Souza, o prazo está mantido."

    resultado_1, _ = anonimizar_texto(ata_1, SECRET_KEY, db_session)
    resultado_2, _ = anonimizar_texto(ata_2, SECRET_KEY, db_session)

    token_1 = resultado_1.split("O professor ")[1].split(" apresentou")[0]
    token_2 = resultado_2.split("Segundo o professor ")[1].split(", o prazo")[0]
    assert token_1 == token_2


def test_reprocessar_o_mesmo_texto_e_idempotente(db_session):
    primeira_vez, _ = anonimizar_texto(TEXTO_ABERTURA, SECRET_KEY, db_session)
    segunda_vez, _ = anonimizar_texto(TEXTO_ABERTURA, SECRET_KEY, db_session)

    assert primeira_vez == segunda_vez


def test_pessoas_diferentes_geram_tokens_diferentes(db_session):
    # filtra pelos tokens que aparecem no proprio resultado, nao pela tabela
    # inteira — contra um Postgres de dev com o corpus real ja ingerido, um
    # count() sem filtro contaria tambem entidades de outras execucoes
    resultado, _ = anonimizar_texto(TEXTO_ABERTURA, SECRET_KEY, db_session)
    tokens_no_resultado = set(re.findall(r"PESSOA_\d+", resultado))

    entidades = (
        db_session.query(EntidadeAnonimizada)
        .filter(EntidadeAnonimizada.token.in_(tokens_no_resultado))
        .all()
    )
    assert len(entidades) == 2
    assert {e.token for e in entidades} == tokens_no_resultado


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

    resultado_a, _ = anonimizar_texto(texto, SECRET_KEY, db_session)
    resultado_b, _ = anonimizar_texto(texto, OUTRA_SECRET_KEY, db_session)

    token_a = resultado_a.split("O professor ")[1].split(" apresentou")[0]
    token_b = resultado_b.split("O professor ")[1].split(" apresentou")[0]
    assert token_a != token_b


def test_mesmo_numero_de_processo_gera_sempre_o_mesmo_token(db_session):
    texto = "O processo 23068.001234/2025-11 foi distribuído para relatoria."

    resultado_1, _ = anonimizar_texto(texto, SECRET_KEY, db_session)
    resultado_2, _ = anonimizar_texto(texto, SECRET_KEY, db_session)

    assert resultado_1 == resultado_2
    # filtra pelo token especifico gerado, nao pela tabela inteira — mesmo
    # motivo do teste acima
    token = re.search(r"PROCESSO_\d+", resultado_1).group(0)
    entidades = db_session.query(EntidadeAnonimizada).filter_by(token=token).all()
    assert len(entidades) == 1


def test_texto_sem_pessoas_ou_processos_fica_inalterado(db_session):
    texto = "Ata da reunião ordinária, sem menção a quórum."
    resultado, substituicoes = anonimizar_texto(texto, SECRET_KEY, db_session)
    assert resultado == texto
    assert substituicoes == []


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


def test_recortar_sobreposicao_preserva_pessoa_sem_conflito():
    pessoas = [(0, 10)]
    processos = [(20, 30)]
    assert _recortar_sobreposicao(pessoas, processos) == pessoas


def test_recortar_sobreposicao_recorta_pessoa_grudada_no_numero():
    # simula "Silva23068.001234/2025-11": o NER errou o limite e incluiu
    # os primeiros digitos do numero de processo dentro do span de PESSOA
    pessoas = [(0, 20)]
    processos = [(15, 40)]
    assert _recortar_sobreposicao(pessoas, processos) == [(0, 15)]


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

    resultado, _ = anonimizar_texto(texto, SECRET_KEY, db_session)

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

    resultado, _ = anonimizar_texto(texto, SECRET_KEY, db_session)

    assert "João da Silva Souza" not in resultado
    assert "PESSOA_" in resultado


def test_anonimizar_texto_retorna_substituicoes_com_delta_de_tamanho(db_session):
    # regressao achado #1: quem precisa reprojetar um offset calculado sobre
    # o texto original (ex.: paginas_offsets, calculado pre-anonimizacao)
    # precisa saber onde cada substituicao ocorreu e quanto ela deslocou o
    # texto — o token tem tamanho fixo, diferente do nome/processo real que
    # substitui.
    texto = "O professor João da Silva Souza apresentou o relatório."
    resultado, substituicoes = anonimizar_texto(texto, SECRET_KEY, db_session)

    nome = "João da Silva Souza"
    inicio_nome = texto.index(nome)
    assert substituicoes == [(inicio_nome, len(resultado) - len(texto))]


def test_remapear_offsets_soma_delta_das_substituicoes_anteriores():
    # substituicao em 5 encolhe 3 chars; substituicao em 12 cresce 2 chars.
    # offset exatamente no inicio de uma substituicao ainda nao foi
    # deslocado por ela (ela desloca o que vem DEPOIS de si mesma)
    substituicoes = [(5, -3), (12, 2)]
    assert remapear_offsets([0, 3, 5, 10, 20], substituicoes) == [0, 3, 5, 7, 19]


def test_remapear_offsets_sem_substituicoes_retorna_offsets_inalterados():
    assert remapear_offsets([0, 10, 20], []) == [0, 10, 20]


def test_cpf_e_substituido_por_token(db_session):
    texto = "CPF 150.233.587-55 cadastrado no processo seletivo."
    resultado, _ = anonimizar_texto(texto, SECRET_KEY, db_session)
    assert "150.233.587-55" not in resultado
    assert "CPF_" in resultado


def test_rg_e_substituido_por_token(db_session):
    texto = "Portador do RG 28631510-6, compareceu à sessão."
    resultado, _ = anonimizar_texto(texto, SECRET_KEY, db_session)
    assert "28631510-6" not in resultado
    assert "RG_" in resultado


def test_email_pessoal_e_substituido_por_token(db_session):
    texto = "Contato: marcus.v.almeida@ufes.br para mais informações."
    resultado, _ = anonimizar_texto(texto, SECRET_KEY, db_session)
    assert "marcus.v.almeida@ufes.br" not in resultado
    assert "EMAIL_" in resultado


def test_email_institucional_permanece_intacto(db_session):
    texto = "Encaminhar dúvidas para secretaria.ct@ufes.br."
    resultado, _ = anonimizar_texto(texto, SECRET_KEY, db_session)
    assert "secretaria.ct@ufes.br" in resultado
    assert "EMAIL_" not in resultado


def test_pessoa_colada_em_email_nao_corrompe_a_saida(db_session, monkeypatch):
    # regressao do achado (d): o NER as vezes reconhece so um fragmento de
    # nome dentro do local-part de um e-mail sem espaco (ex.: "v.almeida"
    # dentro de "marcus.v.almeida@ufes.br"), produzindo token de PESSOA
    # colado com o resto do e-mail cru em vez do e-mail inteiro anonimizado
    texto = "Assinado eletronicamente por marcus.v.almeida@ufes.br em anexo."
    inicio_email = texto.index("marcus.v.almeida@ufes.br")
    monkeypatch.setattr(
        cleaner,
        "_achar_entidades_pessoa",
        lambda _texto: [(inicio_email + len("marcus."), inicio_email + len("marcus.v.almeida"))],
    )

    resultado, _ = anonimizar_texto(texto, SECRET_KEY, db_session)

    assert "marcus.v.almeida@ufes.br" not in resultado
    assert "PESSOA_" not in resultado
    assert resultado.startswith("Assinado eletronicamente por EMAIL_")
    assert resultado.endswith(" em anexo.")


def test_processo_fora_do_prefixo_sipac_padrao_e_substituido(db_session):
    # achado (f): RE_PROCESSO_SIPAC so pegava o prefixo 23068. (SIPAC-UFES);
    # doc 462 do corpus real tem um protocolo Fala.BR/CGU (23546.) no mesmo
    # formato NNNNN.NNNNNN/NNNN-NN que tambem precisa ser anonimizado
    texto = "Protocolo 23546.071495/2021-22 registrado na ouvidoria."
    resultado, _ = anonimizar_texto(texto, SECRET_KEY, db_session)
    assert "23546.071495/2021-22" not in resultado
    assert "PROCESSO_" in resultado
