from tests.recuperacao.conftest import criar_documento


def test_pdf_do_documento_e_servido_inline(cliente_api, db_session, tmp_path):
    arquivo = tmp_path / "ata_pdf.pdf"
    arquivo.write_bytes(b"%PDF-1.4 conteudo de teste")
    documento = criar_documento(db_session, nome_arquivo="ata_pdf.pdf", url_origem=str(arquivo))

    resposta = cliente_api.get(f"/documentos/{documento.id_documento}/pdf")

    assert resposta.status_code == 200
    assert resposta.content == b"%PDF-1.4 conteudo de teste"
    assert resposta.headers["content-type"] == "application/pdf"
    assert resposta.headers["content-disposition"].startswith("inline")


def test_pdf_de_documento_inexistente_da_404(cliente_api):
    resposta = cliente_api.get("/documentos/999999999/pdf")

    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "Documento não encontrado."}


def test_pdf_com_arquivo_ausente_da_404_sem_vazar_caminho(cliente_api, db_session, tmp_path):
    documento = criar_documento(
        db_session, nome_arquivo="sumiu.pdf", url_origem=str(tmp_path / "sumiu.pdf")
    )

    resposta = cliente_api.get(f"/documentos/{documento.id_documento}/pdf")

    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "Documento não encontrado."}
    assert str(tmp_path) not in resposta.text


def test_pdf_com_id_nao_numerico_da_422(cliente_api):
    assert cliente_api.get("/documentos/abc/pdf").status_code == 422


def test_pdf_passa_pelo_path_seguro_do_coletor(cliente_api, db_session, tmp_path, monkeypatch):
    arquivo = tmp_path / "longo.pdf"
    arquivo.write_bytes(b"%PDF-1.4 caminho longo")
    documento = criar_documento(
        db_session, nome_arquivo="longo.pdf", url_origem="C:\\caminho\\sem\\prefixo.pdf"
    )
    monkeypatch.setattr("app.api.rotas.path_seguro", lambda caminho: arquivo)

    resposta = cliente_api.get(f"/documentos/{documento.id_documento}/pdf")

    assert resposta.status_code == 200
    assert resposta.content == b"%PDF-1.4 caminho longo"
