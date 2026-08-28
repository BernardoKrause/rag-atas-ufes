from datetime import date

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
