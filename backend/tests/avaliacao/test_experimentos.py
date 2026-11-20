from app.avaliacao.experimentos import variantes_setor
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
