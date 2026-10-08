from datetime import date

import pytest

from app.ingestion.enriquecedor import CamposEnriquecidos, enriquecer_e_persistir
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta


def test_enriquecer_e_persistir_preenche_campos_do_item(db_session, monkeypatch):
    import app.ingestion.enriquecedor as mod
    monkeypatch.setitem(
        mod.CONFIG_ENRIQUECEDOR, ("B", "CT"),
        lambda texto, data_reuniao: CamposEnriquecidos(
            assunto="assunto teste", tipo_desfecho="Aprovado", resultado_votacao="unanimidade",
            encaminhamento=None, ato_emitido=None, departamento_origem="INFORMATICA",
        ),
    )

    documento = Documento(
        nome_arquivo="x.pdf", url_origem="x.pdf", centro="CT", campus="Goiabeiras",
        tipo_orgao="B", orgao="CT", data_reuniao=date(2025, 1, 1), texto_limpo="texto",
    )
    db_session.add(documento)
    db_session.flush()
    item = ItemPauta(
        documento_id=documento.id_documento, item_id_canonico="1_PAUTA_1",
        secao="PAUTA", numero_item="1", texto="PAUTA 1: texto do item",
    )
    db_session.add(item)
    db_session.flush()

    enriquecer_e_persistir(documento, [item], db_session)

    assert item.assunto == "assunto teste"
    assert item.tipo_desfecho == "Aprovado"
    assert item.departamento_origem == "INFORMATICA"


def test_fragmento_herda_assunto_do_primeiro_fragmento_do_item(db_session, monkeypatch):
    import app.ingestion.enriquecedor as mod
    monkeypatch.setitem(
        mod.CONFIG_ENRIQUECEDOR, ("B", "CT"),
        lambda texto, data_reuniao: CamposEnriquecidos(texto, None, None, None, None, None),
    )

    documento = Documento(
        nome_arquivo="f.pdf", url_origem="f.pdf", centro="CT", campus="Goiabeiras",
        tipo_orgao="B", orgao="CT", data_reuniao=date(2025, 1, 1), texto_limpo="texto",
    )
    db_session.add(documento)
    db_session.flush()
    inicio = ItemPauta(
        documento_id=documento.id_documento, item_id_canonico="3_PAUTA_1",
        secao="PAUTA", numero_item="1", fragmento_indice=0, texto="PAUTA 1: inicio do item",
    )
    continuacao = ItemPauta(
        documento_id=documento.id_documento, item_id_canonico="3_PAUTA_1_F1",
        secao="PAUTA", numero_item="1", fragmento_indice=1, texto="meio do texto do item",
    )
    db_session.add_all([inicio, continuacao])
    db_session.flush()

    enriquecer_e_persistir(documento, [inicio, continuacao], db_session)

    assert continuacao.assunto == inicio.assunto


def test_enriquecer_e_persistir_e_idempotente(db_session, monkeypatch):
    import app.ingestion.enriquecedor as mod
    chamadas = []
    def _fake(texto, data_reuniao):
        chamadas.append(texto)
        return CamposEnriquecidos(None, "Aprovado", None, None, None, None)
    monkeypatch.setitem(mod.CONFIG_ENRIQUECEDOR, ("B", "CT"), _fake)

    documento = Documento(
        nome_arquivo="y.pdf", url_origem="y.pdf", centro="CT", campus="Goiabeiras",
        tipo_orgao="B", orgao="CT", data_reuniao=date(2025, 1, 1), texto_limpo="texto",
    )
    db_session.add(documento)
    db_session.flush()
    item = ItemPauta(
        documento_id=documento.id_documento, item_id_canonico="2_PAUTA_1",
        secao="PAUTA", numero_item="1", texto="PAUTA 1: texto do item",
    )
    db_session.add(item)
    db_session.flush()

    enriquecer_e_persistir(documento, [item], db_session)
    enriquecer_e_persistir(documento, [item], db_session)

    assert len(chamadas) == 2
    assert item.tipo_desfecho == "Aprovado"


def test_extrair_corpo_sem_marcador_ct():
    from app.ingestion.enriquecedor import extrair_corpo_sem_marcador
    texto = 'PAUTA 2: Processo digital nº 23068.007249/2025-23 - homologação - Departamento de Informática - Interrupção. Decisão: Homologado(a).'
    corpo = extrair_corpo_sem_marcador("PAUTA", texto)
    assert corpo.startswith("Processo digital")


def test_extrair_corpo_sem_marcador_pontilhado():
    from app.ingestion.enriquecedor import extrair_corpo_sem_marcador
    texto = '4.3. Apreciação com sugestões para aprimoramento da proposta. Decisão: Aprovado.'
    corpo = extrair_corpo_sem_marcador("INFORMES", texto)
    assert corpo.startswith("Apreciação")


def test_extrair_ct_aprovado_com_departamento():
    from app.ingestion.enriquecedor import extrair_ct
    texto = (
        'PAUTA 2: Processo digital nº 23068.007249/2025-23 - homologação de "ad referendum" '
        '- Departamento de Informática - Interrupção, a partir do dia 17/05/2025, da licença '
        'para capacitação do Prof. PESSOA_0001. Decisão: Homologado(a).'
    )
    campos = extrair_ct(texto, date(2025, 6, 6))
    assert campos.tipo_desfecho == "Aprovado"
    assert campos.departamento_origem == "INFORMATICA"
    assert "Interrupção" in campos.assunto
    assert "Decisão" not in campos.assunto


def test_extrair_ct_retirado_sem_departamento():
    from app.ingestion.enriquecedor import extrair_ct
    texto = 'PAUTA 5: Processo digital nº 23068.000001/2025-00 - Análise de recurso. Decisão: Retirado(a).'
    campos = extrair_ct(texto, date(2025, 6, 6))
    assert campos.tipo_desfecho == "Retirado"
    assert campos.departamento_origem is None


def test_extrair_ct_departamento_terminado_por_ponto():
    from app.ingestion.enriquecedor import extrair_ct

    # excerto real do item id=15079 (doc_id=492): nome do departamento e
    # terminado por ponto final, nao por hifen, ao contrario do exemplo de
    # calibracao original.
    texto = (
        'PAUTA 2: Documento avulso nº PROCESSO_2822 - Solicitação de ações para o '
        'Monitoramento do Estudante Iniciante (MEI) - 2024/1 - Departamento de '
        'Computação e Eletrônica (DCE). Apreciação da solicitação da CCCC/Ceunes e '
        'Documento avulso nº PROCESSO_2821 DCE-Solicitação de ações para o '
        'Monitoramento do Estudante Iniciante (MEI) - 2024/1. Decisão: Aprovado(a) '
        'por unanimidade.'
    )
    campos = extrair_ct(texto, date(2025, 6, 6))
    assert campos.departamento_origem == "COMPUTACAO_E_ELETRONICA_DCE"
    assert len(campos.departamento_origem) <= 60


def test_extrair_ct_departamento_incidental_excede_limite_retorna_none():
    from app.ingestion.enriquecedor import extrair_ct

    # excerto real do item id=16349 (doc_id=540): "Departamento de" aparece de
    # forma incidental numa afiliacao de membro externo de comissao, sem
    # hifen nem ponto proximos para delimitar o nome - mesmo com o terminador
    # ampliado (hifen OU ponto), o trecho capturado ainda estoura os 60
    # caracteres da coluna (o primeiro ponto so aparece bem mais adiante, em
    # "Profa."). Guarda defensiva deve descartar em vez de persistir uma
    # string truncada/garbage.
    texto = (
        'PAUTA 4: Processo PROCESSO_3010 - Solicita apreciação de nomes para compor '
        'Comissão Especial para avaliar a promoção do Professor PESSOA_0001, da '
        'Classe D para a Classe E, conforme sugestão a seguir: Membro Interno: Prof. '
        'PESSOA_0002 - Departamento de Ciências Agrárias e Biológicas, Centro '
        'Universitário Norte do Espírito Santo, Universidade Federal do Espírito '
        'Santo (UFES); Membro Externo: Profa. PESSOA_0003 Emissão: 25/07/2024 '
        '09:23:44 Página 2/6 Documento assinado digitalmente conforme descrito '
        'no(s) Protocolo(s) de Assinatura constante(s) neste arquivo, de onde é '
        'possível verificar a autenticidade do mesmo. PESSOA_0004 - Decisão: '
        'Aprovado(a) por unanimidade.'
    )
    campos = extrair_ct(texto, date(2025, 6, 6))
    assert campos.departamento_origem is None


def test_extrair_ct_departamento_terminado_por_dois_pontos():
    from app.ingestion.enriquecedor import extrair_ct

    # excerto real do item id=14846 (doc_id=331): lista orcamentaria com
    # departamentos separados por "-" e valores em R$ apos ":". Sem ":" no
    # terminador, a captura avanca ate o valor monetario ("ENGENHARIA_
    # AMBIENTAL_R_58", 26 chars) — passa pela guarda de tamanho em silencio
    # e persiste lixo em vez do nome correto do departamento.
    texto = (
        'PAUTA 24: O senhor Diretor apresentou a proposta de orçamento do Centro '
        'Tecnológico para o ano de 2025. Segue o detalhamento por departamento: '
        '- Departamento de Engenharia Ambiental: R$ 58.751,12; - Departamento de '
        'Engenharia Civil: R$ 61.925,95; - Departamento de Engenharia de Produção: '
        'R$ 75.750,61. Decisão: Aprovado(a) por unanimidade a proposta apresentada '
        'pela Direção do CT.'
    )
    campos = extrair_ct(texto, date(2025, 6, 6))
    assert campos.departamento_origem == "ENGENHARIA_AMBIENTAL"


def test_extrair_ct_contra_fixture_real(db_session):
    from pathlib import Path
    from app.ingestion.pipeline import executar_pipeline
    from app.ingestion.segmentador import segmentar_e_persistir
    from app.ingestion.enriquecedor import enriquecer_e_persistir

    fixtures = Path(__file__).parent.parent / "fixtures" / "atas_sample"
    documentos = executar_pipeline(fixtures, b"chave-de-teste-nao-usar-em-producao", db_session)
    ct = next(d for d in documentos if d.nome_arquivo == "10-2025.pdf")
    itens = segmentar_e_persistir(ct, db_session)

    enriquecer_e_persistir(ct, itens, db_session)

    desfechos = {i.tipo_desfecho for i in itens if i.tipo_desfecho}
    assert desfechos <= {"Aprovado", "Reprovado", "Encaminhado", "Adiado", "Retirado"}
    assert any(i.departamento_origem == "INFORMATICA" for i in itens)


def test_extrair_generico_ignora_encerramento_da_ata_no_ultimo_item():
    from app.ingestion.enriquecedor import extrair_generico

    texto = (
        "1.4 Documento avulso: Atuação no Programa de Pós-Graduação. "
        "Em votação. Aprovado por unanimidade. Nada mais havendo a tratar, "
        "encerrou-se a presente reunião e eu lavrei a presente Ata, que, "
        "após lida e achada conforme, será aprovada e assinada por todos "
        "os membros desta Câmara Departamental."
    )
    campos = extrair_generico(texto, None)
    assert campos.resultado_votacao == "Aprovado por unanimidade"


def test_extrair_generico_aprovacao_de_ata_com_decisao_antes_do_marcador():
    from app.ingestion.enriquecedor import extrair_generico

    texto = (
        "Foi apreciada e aprovada, por unanimidade: 1.1 Ata da Sessão "
        "Ordinária do Conselho Departamental, realizada em 17 de dezembro "
        "de 2024."
    )
    campos = extrair_generico(texto, None)
    assert campos.assunto == "Ata da Sessão Ordinária do Conselho Departamental, realizada em 17 de dezembro de 2024"
    assert campos.tipo_desfecho == "Aprovado"
    assert campos.resultado_votacao == "Foi apreciada e aprovada, por unanimidade"


def test_extrair_generico_aprovado_unanimidade():
    from app.ingestion.enriquecedor import extrair_generico

    texto = '1) Proc. 23068.001234/2025-11 Eleição de coordenador. Aprovado a unanimidade.'
    campos = extrair_generico(texto, None)
    assert campos.tipo_desfecho == "Aprovado"
    assert "unanimidade" in campos.resultado_votacao


def test_extrair_generico_retirado():
    from app.ingestion.enriquecedor import extrair_generico

    texto = '4.3. Apreciação de estudante em situação de desligamento. Ponto de pauta retirado.'
    campos = extrair_generico(texto, None)
    assert campos.tipo_desfecho == "Retirado"


def test_extrair_generico_retirado_de_pauta():
    from app.ingestion.enriquecedor import extrair_generico

    texto = '1.1 Solicitação de bolsa. O item foi retirado de pauta.'
    campos = extrair_generico(texto, None)
    assert campos.tipo_desfecho == "Retirado"


def test_extrair_generico_sem_palavra_chave_retorna_none():
    from app.ingestion.enriquecedor import extrair_generico

    texto = '2.1 Nova Resolução sobre EART, discussão em andamento.'
    campos = extrair_generico(texto, None)
    assert campos.tipo_desfecho is None
    assert campos.assunto == 'Nova Resolução sobre EART, discussão em andamento.'


def test_extrair_generico_remove_marcador_de_abertura_do_assunto():
    from app.ingestion.enriquecedor import extrair_generico

    # o marcador do proprio item ("1.1", "3)") vazava pro assunto e quebrava a
    # chave de merge cross-documento do Assunto no grafo.
    campos = extrair_generico('1.1 Aprovação do calendário acadêmico. Aprovado por unanimidade.', None)
    assert campos.assunto == 'Aprovação do calendário acadêmico'

    campos_outro = extrair_generico('4.2 Aprovação do calendário acadêmico. Aprovado por unanimidade.', None)
    assert campos_outro.assunto == campos.assunto


def test_extrair_generico_nao_remove_numero_que_nao_e_marcador():
    from app.ingestion.enriquecedor import extrair_generico

    campos = extrair_generico('25 de fevereiro de 2025: leitura da ata. Aprovada.', None)
    assert campos.assunto == '25 de fevereiro de 2025: leitura da ata'


def test_normalizar_departamento_sem_alfanumerico_retorna_none():
    from app.ingestion.enriquecedor import _normalizar_departamento

    assert _normalizar_departamento(" -- ") is None
    assert _normalizar_departamento("Informática") == "INFORMATICA"


def test_extrair_ccae_resolucao_setenta_e_nove():
    from app.ingestion.enriquecedor import extrair_ccae

    texto = (
        '3.2 Ajustes de formação. Aprovado por unanimidade. Baixada a RESOLUÇÃO NÚMERO SETENTA '
        'E NOVE, DE VINTE E OITO DE JANEIRO DE DOIS MIL E VINTE E CINCO. Revoga-se a Resolução '
        'CCAE/Ufes nº 62, de 21 de fevereiro de 2024, deste Conselho.'
    )
    campos = extrair_ccae(texto, date(2025, 1, 28))
    assert campos.ato_emitido == "RESOLUCAO_79_2025"
    assert campos.tipo_desfecho == "Aprovado"


def test_extrair_ccae_decisao_tres_barra():
    from app.ingestion.enriquecedor import extrair_ccae

    texto = 'Aprovado por unanimidade. Baixada a DECISÃO NÚMERO TRÊS BARRA DOIS MIL E VINTE E CINCO.'
    campos = extrair_ccae(texto, date(2025, 1, 28))
    assert campos.ato_emitido == "DECISAO_3_2025"


def test_extrair_ccae_sem_ato_emitido():
    from app.ingestion.enriquecedor import extrair_ccae

    texto = '3.3 Processo digital nº 23068.001468/2025-07 – Encaminha, para conhecimento.'
    campos = extrair_ccae(texto, date(2025, 1, 28))
    assert campos.ato_emitido is None


def test_extrair_ccae_contra_fixture_real(db_session):
    from pathlib import Path
    from app.ingestion.pipeline import executar_pipeline
    from app.ingestion.segmentador import segmentar_e_persistir
    from app.ingestion.enriquecedor import enriquecer_e_persistir

    fixtures = Path(__file__).parent.parent / "fixtures" / "atas_sample"
    documentos = executar_pipeline(fixtures, b"chave-de-teste-nao-usar-em-producao", db_session)
    ccae = next(d for d in documentos if d.nome_arquivo == "1_ata_sessao_ordinaria_do_dia_28_de_janeiro_2025.pdf")
    itens = segmentar_e_persistir(ccae, db_session)

    enriquecer_e_persistir(ccae, itens, db_session)

    atos = [i.ato_emitido for i in itens if i.ato_emitido]
    assert "RESOLUCAO_79_2025" in atos
    assert any(a.startswith("DECISAO_") for a in atos)


def test_extrair_generico_contra_fixtures_reais(db_session):
    from pathlib import Path
    from app.ingestion.pipeline import executar_pipeline
    from app.ingestion.segmentador import segmentar_e_persistir
    from app.ingestion.enriquecedor import enriquecer_e_persistir

    fixtures = Path(__file__).parent.parent / "fixtures" / "atas_sample"
    documentos = executar_pipeline(fixtures, b"chave-de-teste-nao-usar-em-producao", db_session)

    from app.ingestion.enriquecedor import extrair_corpo_sem_marcador

    for nome in ["ata_05_02_2025.pdf", "2020.08.17_-_ata_1a_ordinaria_camara_local.pdf",
                 "ata_da_3a_reuniao_ordinaria_colped.pdf", "ata_da_1a_reuniao_ordinaria_-_db_ccens_04-02-2025.docx.pdf"]:
        documento = next(d for d in documentos if d.nome_arquivo == nome)
        itens = segmentar_e_persistir(documento, db_session)
        enriquecer_e_persistir(documento, itens, db_session)
        assert any(i.tipo_desfecho is not None for i in itens), nome
        for item in itens:
            if item.assunto:
                assert extrair_corpo_sem_marcador("", item.assunto) == item.assunto, (nome, item.assunto)


def test_todas_as_variantes_do_segmentador_tem_extrator_no_enriquecedor():
    from app.ingestion.enriquecedor import _obter_extrator
    from app.ingestion.segmentador import CONFIG_VARIANTES

    for tipo_orgao, centro in CONFIG_VARIANTES:
        _obter_extrator(tipo_orgao, centro)  # nao deve levantar ValueError


@pytest.mark.parametrize("texto", [
    "1.1 Informes. Foi informada a entrada da servidora PESSOA_163997, aprovada no último concurso público para Taes da Ufes no lugar da servidora PESSOA_163996 na Secretaria da Direção.",
    "1.2 A proposta de informatização dos pedidos de 3ª etapa ainda não foi aprovada na Ufes e teve um revés com a aposentadoria da PESSOA_164335, do DRCA.",
    "1.3 Ademais, como a busca consumiu algum tempo, o acolhimento precisou ser adiado para que seja feita a divulgação adequada.",
    "1.4 Mencionou que a situação já foi encaminhada para Direção do Centro de Educação e que o setor buscará orientação junto à PROGEP.",
    "1.5 Sabemos que pela Legislação em vigor, o aluno com mais de 25% de faltas já está automaticamente reprovado na disciplina que ele faltou.",
    "1.6 Alguns alunos não poderiam estar participando, por terem sido reprovados e alguns colado grau antecipado.",
])
def test_extrair_generico_palavra_chave_em_narrativa_nao_gera_desfecho(texto):
    from app.ingestion.enriquecedor import extrair_generico

    campos = extrair_generico(texto, None)
    assert campos.tipo_desfecho is None
    assert campos.resultado_votacao is None


def test_extrair_generico_parecer_longo_usa_a_frase_da_votacao():
    from app.ingestion.enriquecedor import extrair_generico

    texto = (
        "2.1 Parecer sobre recurso. O relator concluiu pelo indeferimento, por ter o candidato "
        "sido reprovado na prova de aptidão didático-prática. Após discussão, o parecer foi "
        "colocado em votação e aprovado por unanimidade."
    )
    campos = extrair_generico(texto, None)
    assert campos.tipo_desfecho == "Aprovado"
    assert "votação" in campos.resultado_votacao


@pytest.mark.parametrize("texto,esperado", [
    ("1.1 Calendário. Em discussão. Em votação. Aprovado por unanimidade.", "Aprovado"),
    ("1.1 Calendário. Após discussão, o calendário foi aprovado por unanimidade.", "Aprovado"),
    ("1.1 Designação. Posta em votação, a designação foi homologada por unanimidade.", "Aprovado"),
    ("1.1 Tema. Em apreciação, em votação, aprovado por unanimidade dos presentes.", "Aprovado"),
    ("1.1 Diagnóstico do ensino de graduação no Centro de Educação – ano 2020. Retirado de pauta.", "Retirado"),
    ("1.1 Constituição da Comissão Própria de Avaliação do Curso de Pedagogia. Retirado de Pauta. EM DISCUSSÃO. APROVADO.", "Aprovado"),
    ("1.1 Tema. Sob deliberação, o encaminhamento aprovado por unanimidade.", "Aprovado"),
    ("1.1 Solicitação. O item foi retirado de pauta e voltará depois.", "Retirado"),
    ("4.3. Apreciação de estudante. Ponto de pauta retirado.", "Retirado"),
])
def test_extrair_generico_desfechos_validos_continuam(texto, esperado):
    from app.ingestion.enriquecedor import extrair_generico

    assert extrair_generico(texto, None).tipo_desfecho == esperado


def test_extrair_generico_retirado_no_fim_so_vale_para_retirado():
    from app.ingestion.enriquecedor import extrair_generico

    assert extrair_generico("1.1 Tema discutido. O processo foi adiado.", None).tipo_desfecho is None
    assert extrair_generico("1.1 Tema discutido. O processo foi aprovado.", None).tipo_desfecho is None


def test_extrair_generico_resultado_votacao_nao_quebra_em_abreviacao():
    from app.ingestion.enriquecedor import extrair_generico

    texto = (
        "1.1 Processo de progressão. Em apreciação, após relato e parecer favorável do conselheiro "
        "professor Dr. PESSOA_164023 foi aprovado por unanimidade."
    )
    campos = extrair_generico(texto, None)
    assert campos.resultado_votacao == (
        "Em apreciação, após relato e parecer favorável do conselheiro professor Dr. PESSOA_164023 "
        "foi aprovado por unanimidade"
    )


def test_extrair_generico_resultado_votacao_termina_na_frase():
    from app.ingestion.enriquecedor import extrair_generico

    texto = "1.1 Tema. Em votação. Aprovado por unanimidade. Baixada a DECISÃO NÚMERO SETENTA E CINCO BARRA DOIS MIL E VINTE E CINCO."
    campos = extrair_generico(texto, None)
    assert campos.resultado_votacao == "Aprovado por unanimidade"


def test_extrair_ccae_mantem_ato_com_resultado_delimitado():
    from app.ingestion.enriquecedor import extrair_ccae

    texto = "3.1 Tema. Em votação. Aprovado por unanimidade. Baixada a DECISÃO NÚMERO SETENTA E CINCO BARRA DOIS MIL E VINTE E CINCO."
    campos = extrair_ccae(texto, date(2025, 3, 1))
    assert campos.ato_emitido == "DECISAO_75_2025"
    assert campos.resultado_votacao == "Aprovado por unanimidade"


def test_extrair_ct_resultado_votacao_termina_na_primeira_frase():
    from app.ingestion.enriquecedor import extrair_ct

    texto = (
        "PAUTA 3: Processo digital nº 23068.000001/2025-00 - Recurso. Decisão: Homologado(a) por maioria. "
        "Para fundamentar que não concorda com a homologação do ponto de pauta, o conselheiro PESSOA_8903, informou que votou contra."
    )
    campos = extrair_ct(texto, date(2025, 6, 6))
    assert campos.tipo_desfecho == "Aprovado"
    assert campos.resultado_votacao == "por maioria."


@pytest.mark.parametrize("texto", [
    "– Resposta que os alunos receberam sobre o tema.",
    "- Resposta que os alunos receberam sobre o tema.",
    "— Resposta que os alunos receberam sobre o tema.",
])
def test_extrair_corpo_sem_marcador_remove_traco_inicial(texto):
    from app.ingestion.enriquecedor import extrair_corpo_sem_marcador

    assert extrair_corpo_sem_marcador("", "1.2 " + texto) == "Resposta que os alunos receberam sobre o tema."


FRASE_VOTACAO = "Em votação, o parecer foi aprovado por unanimidade dos presentes."


def _texto_longo(inicio: str, fim: str, tamanho: int = 7000) -> str:
    enchimento = "A comissão discutiu detalhadamente o relatório apresentado pela relatora. "
    meio = enchimento * (tamanho // len(enchimento))
    return f"{inicio} {meio}{fim}"


def _persistir_fragmentos(db_session, texto):
    from app.ingestion.segmentador import dividir_fragmentos
    documento = Documento(
        nome_arquivo="g.pdf", url_origem="g.pdf", centro="CCJE", campus="Goiabeiras",
        tipo_orgao="A", orgao="CCJE", data_reuniao=date(2025, 1, 1), texto_limpo="texto",
    )
    db_session.add(documento)
    db_session.flush()
    itens = [
        ItemPauta(
            documento_id=documento.id_documento, item_id_canonico=f"teste{documento.id_documento}_PAUTA_3_F{i}",
            secao="PAUTA", numero_item="3", fragmento_indice=i, texto=fragmento,
        )
        for i, fragmento in enumerate(dividir_fragmentos(texto))
    ]
    db_session.add_all(itens)
    db_session.flush()
    enriquecer_e_persistir(documento, itens, db_session)
    return itens


def test_reconstruir_texto_do_item_e_inverso_de_dividir_fragmentos():
    from app.ingestion.enriquecedor import reconstruir_texto_do_item
    from app.ingestion.segmentador import dividir_fragmentos
    texto = _texto_longo("PAUTA 3: Análise do parecer.", FRASE_VOTACAO, 7500)
    fragmentos = dividir_fragmentos(texto)
    assert len(fragmentos) > 2
    assert reconstruir_texto_do_item(fragmentos) == texto
    assert reconstruir_texto_do_item([texto[:100]]) == texto[:100]


def test_todos_os_fragmentos_recebem_os_campos_do_item_completo(db_session):
    itens = _persistir_fragmentos(db_session, _texto_longo("PAUTA 3: Análise do parecer.", FRASE_VOTACAO))

    assert len(itens) > 2
    assert {i.tipo_desfecho for i in itens} == {"Aprovado"}
    assert {i.resultado_votacao for i in itens} == {FRASE_VOTACAO.rstrip(".")}
    assert len({i.assunto for i in itens}) == 1


def test_frase_de_votacao_que_cruza_a_fronteira_do_fragmento_vem_inteira(db_session):
    from app.ingestion.segmentador import TAMANHO_MAX_FRAGMENTO
    frase = "Em votação, o parecer da comissão sobre o relatório foi aprovado por unanimidade."
    prefixo = "PAUTA 3: Análise. "
    enchimento = "A comissão discutiu o relatório apresentado. "
    antes = (prefixo + enchimento * 200)[:TAMANHO_MAX_FRAGMENTO - 30]
    antes = antes[:antes.rindex(".") + 1]
    itens = _persistir_fragmentos(db_session, antes + " " + frase + " Encerrada a discussão.")

    assert len(itens) == 2
    assert frase not in itens[0].texto and frase[:10] in itens[0].texto
    assert {i.resultado_votacao for i in itens} == {frase.rstrip(".")}
    assert {i.tipo_desfecho for i in itens} == {"Aprovado"}


def test_fragmentos_sem_desfecho_em_nenhum_ficam_sem_desfecho(db_session):
    itens = _persistir_fragmentos(db_session, _texto_longo("PAUTA 3: Informes gerais.", "Fim dos informes."))

    assert {i.tipo_desfecho for i in itens} == {None}
    assert {i.encaminhamento for i in itens} == {None}


def test_ultimo_desfecho_do_item_vale_para_todos_os_fragmentos(db_session):
    texto = _texto_longo(
        "PAUTA 3: Em votação, o ponto foi aprovado por unanimidade.",
        "Em nova votação, o ponto foi reprovado por maioria.",
    )
    itens = _persistir_fragmentos(db_session, texto)

    assert {i.tipo_desfecho for i in itens} == {"Reprovado"}


def test_encaminhamento_apos_dois_pontos():
    from app.ingestion.enriquecedor import extrair_encaminhamento
    assert extrair_encaminhamento(
        "Assim, a Coordenadora propôs este encaminhamento: realizar uma reunião com os secretários "
        "do Colegiado para ouvir suas contribuições sobre o documento. Aprovado por unanimidade."
    ) == "realizar uma reunião com os secretários do Colegiado para ouvir suas contribuições sobre o documento"
    assert extrair_encaminhamento(
        "O Presidente PESSOA_165296 apresenta sua sugestão de encaminhamento: um pedido de criação "
        "da diretoria acadêmica. Aprovado."
    ) == "um pedido de criação da diretoria acadêmica"
    assert extrair_encaminhamento(
        "Por fim, o encaminhamento de uma proposta momentânea do Departamento foi: que a subcoordenação "
        "de curso assuma a coordenação de estágio. Aprovado."
    ) == "que a subcoordenação de curso assuma a coordenação de estágio"


def test_encaminhamento_com_destino():
    from app.ingestion.enriquecedor import extrair_encaminhamento
    assert extrair_encaminhamento(
        "Recomendo a aprovação do relatório e do pedido de renovação e solicito encaminhamento "
        "às instâncias competentes."
    ) == "encaminhamento às instâncias competentes"
    assert extrair_encaminhamento(
        "Sou, portanto, favorável à sua aprovação e encaminhamento para registro junto à "
        "Pró-Reitoria de Extensão."
    ) == "encaminhamento para registro junto à Pró-Reitoria de Extensão"


@pytest.mark.parametrize("corpo", [
    "Relatou sobre a situação de ausência da servidora PESSOA_164476, que interferiu no andamento "
    "de alguns encaminhamentos do setor.",
    "A dinâmica no segundo dia do Fórum foi a formação de grupos de trabalho para pensar "
    "encaminhamentos a respeito do que se faria.",
    "Art. 17º A diretoria é a instância responsável pelo encaminhamento e execução das atividades "
    "cotidianas da entidade.",
    "A Chefe do Departamento propôs como encaminhamento colocar em votação a Proposta 2.",
])
def test_encaminhamento_rejeita_casos_genericos_e_procedimentais(corpo):
    from app.ingestion.enriquecedor import extrair_encaminhamento
    assert extrair_encaminhamento(corpo) is None


def test_extrair_generico_preenche_encaminhamento_somente_com_desfecho():
    from app.ingestion.enriquecedor import extrair_generico
    com = extrair_generico(
        "PAUTA 1: Parecer. Sou favorável à sua aprovação e encaminhamento para registro junto à "
        "Pró-Reitoria de Extensão. Em votação, aprovado por unanimidade.", date(2025, 1, 1),
    )
    assert com.tipo_desfecho == "Aprovado"
    assert com.encaminhamento == "encaminhamento para registro junto à Pró-Reitoria de Extensão"

    sem = extrair_generico(
        "PAUTA 1: Informe. Relatou sobre a ausência da servidora, que interferiu no andamento de "
        "alguns encaminhamentos: algo importante.", date(2025, 1, 1),
    )
    assert sem.tipo_desfecho is None
    assert sem.encaminhamento is None


def test_encaminhamento_para_votacao_e_procedimental_e_nao_conta():
    from app.ingestion.enriquecedor import extrair_encaminhamento
    assert extrair_encaminhamento("Colocou o encaminhamento para votação do Colegiado.") is None
    assert extrair_encaminhamento("O encaminhamento a votação foi aprovado.") is None


@pytest.mark.parametrize("texto,esperado", [
    (
        "3.03 Diretrizes. Solicitamos que se dê conhecimento ao colegiado, para melhor andamento dos processos e esclarecimento de todos.” As diretrizes foram aprovadas por unanimidade.",
        "As diretrizes foram aprovadas por unanimidade",
    ),
    (
        "3.03 Sistema. O prazo não seria flexibilizado e seria aplicado apenas a falhas de sistema.” Posto o assunto em discussão e votação, a proposta foi aprovada por unanimidade.",
        "Posto o assunto em discussão e votação, a proposta foi aprovada por unanimidade",
    ),
])
def test_extrair_generico_fim_de_frase_seguido_de_aspas(texto, esperado):
    from app.ingestion.enriquecedor import extrair_generico

    assert extrair_generico(texto, None).resultado_votacao == esperado
