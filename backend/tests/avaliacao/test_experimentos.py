from app.avaliacao.experimentos import etapa_setor, variantes_setor
from app.recuperacao.setor import RE_SETOR


def test_variantes_de_setor_de_centro():
    variantes = variantes_setor("Qual foi a decisão sobre os PADs no setor CAR?", "CAR")

    assert variantes == {
        "original": "Qual foi a decisão sobre os PADs no setor CAR?",
        "sem_setor": "Qual foi a decisão sobre os PADs?",
        "sigla_solta": "Qual foi a decisão sobre os PADs no CAR?",
        "nome_por_extenso": "Qual foi a decisão sobre os PADs no Centro de Artes?",
    }


def test_variantes_de_setor_de_departamento_com_barra():
    variantes = variantes_setor("O que foi decidido sobre a comissão no setor CCAE / DEAL?", "CCAE_DEAL")

    assert variantes["sigla_solta"] == "O que foi decidido sobre a comissão no CCAE / DEAL?"
    assert variantes["nome_por_extenso"] == "O que foi decidido sobre a comissão no Departamento de Engenharia de Alimentos?"
    assert not any(RE_SETOR.search(texto) for nome, texto in variantes.items() if nome != "original")


def test_pergunta_sem_setor_so_tem_a_original():
    assert variantes_setor("Qual foi a decisão sobre os PADs?", None) == {"original": "Qual foi a decisão sobre os PADs?"}


def test_etapa_seletor_passa_o_orgao_e_usa_original_e_sem_setor(tmp_path, monkeypatch):
    chamadas = []

    def recuperar_falso(enunciado, *args, orgao=None, registro=None, **kwargs):
        chamadas.append((enunciado, orgao))
        registro.update({"orgao": orgao, "ids_finais": []})
        return []

    monkeypatch.setattr("app.recuperacao.orquestrador.recuperar", recuperar_falso)
    referencias = [{"identificador": "P1", "enunciado": "Qual foi a decisão sobre os PADs no setor CAR?", "orgao": "CAR"}]

    total = etapa_setor(referencias, tmp_path, None, None, None, seletor=True)

    assert total == 4
    assert {(enunciado, orgao) for enunciado, orgao in chamadas} == {
        ("Qual foi a decisão sobre os PADs no setor CAR?", "CAR"),
        ("Qual foi a decisão sobre os PADs?", "CAR"),
    }
    assert (tmp_path / "seletor.jsonl").exists()
    assert not (tmp_path / "setor.jsonl").exists()
