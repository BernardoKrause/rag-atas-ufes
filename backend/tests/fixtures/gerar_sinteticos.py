import sys
from pathlib import Path

import fitz

AQUI = Path(__file__).parent
FONTE_PADRAO = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
A4 = fitz.paper_rect("a4")
MARGEM_X, TOPO, ENTRELINHA, CORPO = 50, 50, 13, 9

CABECALHO_CCENS = [
    "Universidade Federal do Espírito Santo",
    "Centro de Ciências Exatas, Naturais e da Saúde",
]


def _escrever(pagina: fitz.Page, linhas: list[str], fonte: str) -> None:
    y = TOPO
    for linha in linhas:
        if all(ord(c) < 256 for c in linha):
            pagina.insert_text((MARGEM_X, y), linha, fontname="helv", fontsize=CORPO)
        else:
            pagina.insert_text((MARGEM_X, y), linha, fontname="F0", fontfile=fonte, fontsize=CORPO)
        y += ENTRELINHA


def _pdf_de_texto(destino: Path, paginas: list[list[str]], fonte: str) -> None:
    documento = fitz.open()
    for linhas in paginas:
        _escrever(documento.new_page(width=A4.width, height=A4.height), linhas, fonte)
    documento.subset_fonts()
    destino.parent.mkdir(parents=True, exist_ok=True)
    documento.save(destino, garbage=4, deflate=True)


def ccens_db() -> list[list[str]]:
    cabecalho = CABECALHO_CCENS + ["Departamento de Biologia"]
    return [
        cabecalho + [
            "ATA DA 1ª REUNIÃO ORDINÁRIA DA CÂMARA DEPARTAMENTAL DE BIOLOGIA",
            "Aos quatro dias do mês de fevereiro de dois mil e vinte e cinco, às 14h00, na sala de reuniões",
            "do departamento, havendo quórum, reuniu-se a Câmara Departamental sob a presidência",
            "da Profa. Marta Exemplo, chefe do departamento.",
            "1. EXPEDIENTE:",
            "1.1. Comunicado da chefia sobre o calendário fictício do semestre. A câmara tomou ciência.",
            "1.2. Solicitação de afastamento do Prof. Caio Ficticio para participar de congresso.",
            "Aprovado por unanimidade.",
            "2. ORDEM DO DIA:",
            "2.1. Plano de ensino da disciplina BIO00001 Biologia Sintética. O relator apresentou",
            "parecer favorável ao plano.",
            "1",
        ],
        cabecalho + [
            "Programa de Pós-Graduação em Ciências Fictícias: o plano segue sem alteração.",
            "Aprovado por unanimidade.",
            "2.2. Homologação do resultado da monitoria fictícia de 2025/1. Aprovado por unanimidade.",
            "Nada mais havendo a tratar, eu, Lia Modelo, secretária, lavrei a presente ata.",
            "2",
        ],
    ]


def ccens_dc() -> list[list[str]]:
    cabecalho = CABECALHO_CCENS + ["Departamento de Computação"]
    return [
        [" "] + cabecalho + [
            "ATA DA 1ª REUNIÃO DE CARÁTER ORDINÁRIO DA CÂMARA DEPARTAMENTAL DE COMPUTAÇÃO",
            "Aos vinte e nove dias de janeiro, às 9h00, na sala de reuniões, havendo quórum.",
            "1. EXPEDIENTE:",
            "1.1. A chefia informou sobre a reforma fictícia do laboratório do",
        ],
        cabecalho + [
            "Campus e sobre os cursos de graduação atendidos. A câmara tomou ciência.",
            "1.2. Oferta da disciplina COM00001 Computação Sintética. Aprovado por unanimidade.",
        ],
        cabecalho + [
            "Prazos fictícios do semestre e calendário de bancas. Aprovado por unanimidade.",
            "Nada mais havendo a tratar, lavrei a presente ata.",
        ],
    ]


def ccens_dc_2_paginas() -> list[list[str]]:
    cabecalho = CABECALHO_CCENS + ["Departamento de Computação"]
    return [
        [" "] + cabecalho + [
            "ATA DA 8ª REUNIÃO DE CARÁTER ORDINÁRIO DA CÂMARA DEPARTAMENTAL DE COMPUTAÇÃO",
            "Aos vinte e sete dias de junho, às 9h00, na sala de reuniões, havendo quórum.",
            "1. EXPEDIENTE:",
            "1.1. A chefia comunicou o pedido da servidora fictícia Rita Teste, que solicitou a",
        ],
        cabecalho + [
            "exoneração do cargo a partir de julho. A câmara tomou ciência.",
            "Nada mais havendo a tratar, lavrei a presente ata.",
        ],
    ]


def car() -> list[list[str]]:
    return [
        [
            "UNIVERSIDADE FEDERAL DO ESPÍRITO SANTO",
            "CENTRO DE ARTES",
            "ATA DA REUNIÃO DO CONSELHO DEPARTAMENTAL DO CENTRO DE ARTES",
            "Aos cinco dias de fevereiro de dois mil e vinte e cinco, às 9h00, na sala de reuniões do",
            "Centro de Artes, havendo quórum, reuniu-se o Conselho Departamental.",
            "INFORMES: A direção informou sobre a programação fictícia de exposições do semestre e",
            "sobre a manutenção dos ateliês, sem deliberação. Os conselheiros tomaram ciência dos informes.",
            "PAUTA:",
            "1) Processo 23068.000101/2025-11. Plano de atividades docentes do Departamento de Artes",
            "Sintéticas. Relatora: Conselheira Ana Exemplo. Aprovado por unanimidade.",
            "2) Processo 23068.000102/2025-12. Projeto de extensão Oficina Fictícia de Gravura.",
            "Aprovado por unanimidade.",
            "3) Processo 23068.000103/2025-13. Solicitação de licença do Prof. Davi Modelo. Após a",
        ],
        [
            "concessão da solicitação pela chefia, o conselho referendou. Aprovado por unanimidade.",
            "4) Processo 23068.000104/2025-14. Relatório de atividades do laboratório fictício.",
            "Aprovado por unanimidade.",
            "5) Processo 23068.000105/2025-15. Calendário de bancas do curso de Artes Sintéticas.",
            "Aprovado por maioria.",
            "6) Processo 23068.000106/2025-16. Proposta de evento fictício. Retirado de pauta.",
            "Nada mais havendo a tratar, eu, Bia Teste, secretária, lavrei a presente ata.",
        ],
    ]


def ccae() -> list[list[str]]:
    return [
        [
            "UNIVERSIDADE FEDERAL DO ESPÍRITO SANTO",
            "CENTRO DE CIÊNCIAS AGRÁRIAS E ENGENHARIAS",
            "ATA DA 1ª SESSÃO ORDINÁRIA DO CONSELHO DEPARTAMENTAL",
            "Aos vinte e oito dias de janeiro de dois mil e vinte e cinco, às 14h00, na Sala de Reuniões",
            "do Conselho Departamental, havendo quórum, reuniu-se o Conselho sob a presidência",
            "do Diretor Paulo Ficticio.",
            "1. APROVAÇÃO DE ATA:",
            "1.1. Ata da sessão anterior. Aprovada por unanimidade.",
            "2. EXPEDIENTE:",
            "2.1. Ofício fictício da Pró-Reitoria sobre o calendário. O conselho tomou ciência.",
            "2.2. Processo 23068.000201/2025-21. Afastamento do Prof. Igor Exemplo. Aprovado por unanimidade.",
            "3. ORDEM DO DIA:",
            "3.1. Processo 23068.000202/2025-22. Regimento fictício do laboratório de solos. Aprovado por",
            "unanimidade. Baixada a RESOLUÇÃO NÚMERO SETENTA E NOVE, DE VINTE E OITO DE JANEIRO.",
            "3.2. Processo 23068.000203/2025-23. Comissão fictícia de avaliação. Aprovado por",
            "unanimidade. Baixada a DECISÃO NÚMERO DOIS, DE VINTE E OITO DE JANEIRO.",
            "4. COMUNICAÇÕES:",
            "4.1. A direção comunicou a agenda fictícia de visitas técnicas.",
            "Nada mais havendo a tratar, eu, Luiza Modelo, secretária, lavrei a presente ata.",
        ],
    ]


def _rodape_ct(numero: int) -> list[str]:
    return ["Emissão: 11/03/2026 12:00:13", f"Página {numero}/3"]


def ct() -> list[list[str]]:
    abertura = (
        "Ata da 10ª reunião do Conselho Departamental do Centro Tecnológico, realizada às 14h00, "
        "por videoconferência pelo Google Meet, havendo quórum."
    ).split()
    return [
        ["ATA EM APROVAÇÃO", "UNIVERSIDADE FEDERAL DO ESPÍRITO SANTO"] + abertura + [
            "INFORME 1: A direção informou o calendário fictício de 2025/2.",
            "INFORME 2: A coordenação comunicou a semana fictícia de engenharia.",
            "PAUTA 1: Processo 23068.000301/2025-31 - Departamento de Informática - Oferta da",
            "disciplina INF00001 Computação Sintética. Decisão: Aprovado(a) por unanimidade.",
            "PAUTA 2: Processo 23068.000302/2025-32 - Departamento de Engenharia Fictícia -",
            "Projeto de pesquisa sintético. Decisão: Aprovado(a) por unanimidade.",
        ] + _rodape_ct(1),
        ["ATA EM APROVAÇÃO", "UNIVERSIDADE FEDERAL DO ESPÍRITO SANTO"] + [
            "PAUTA 3: Processo 23068.000303/2025-33 - Departamento de Informática - Plano de",
            "trabalho fictício. Decisão: Homologado(a) por unanimidade.",
            "PAUTA 4: Processo 23068.000304/2025-34 - Relatório de estágio fictício.",
            "Decisão: Retirado(a) de pauta.",
            "PAUTA 5: Processo 23068.000305/2025-35 - Convênio sintético. Decisão: Aprovado(a).",
        ] + _rodape_ct(2),
        ["ATA EM APROVAÇÃO", "UNIVERSIDADE FEDERAL DO ESPÍRITO SANTO"] + [
            "PAUTA 6: Processo 23068.000306/2025-36 - Comissão fictícia. Decisão: Aprovado(a).",
            "PAUTA 7: Processo 23068.000307/2025-37 - Edital sintético. Decisão: Aprovado(a).",
            "Nada mais havendo a tratar, eu, Nina Teste, secretária, lavrei a presente ata.",
        ] + _rodape_ct(3),
    ]


def cchn_camara_local() -> list[list[str]]:
    cabecalho = [
        "UNIVERSIDADE FEDERAL DO ESPÍRITO SANTO",
        "CENTRO DE CIÊNCIAS HUMANAS E NATURAIS",
        "CONSELHO DEPARTAMENTAL - CÂMARA LOCAL DE GRADUAÇÃO",
    ]
    return [
        cabecalho + [
            "ATA DA 1ª REUNIÃO ORDINÁRIA DA CÂMARA LOCAL DE GRADUAÇÃO",
            "Aos dezessete dias de agosto, às 14h00, por webconferência, havendo quórum.",
            "1. INFORMES:",
            "1.1. A presidência convidou os coordenadores a parƟcipar do fórum fictício de graduação.",
            "1.2. Calendário fictício de matrículas. A câmara tomou ciência.",
            "2. EXPEDIENTE: EXCLUSÃO DE PAUTA:",
            "2.1. Exclusão do ponto sobre a oferta fictícia. Aprovado por unanimidade.",
            "3. ORDEM DO DIA:",
            "3.1. Diretrizes fictícias de estágio. Aprovado por unanimidade.",
            "3.2. Consulta fictícia à Pró-Reitoria sobre aproveitamento. Aprovado por unanimidade.",
            "3.3. Calendário fictício de colação. Aprovado por unanimidade.",
            "Nada mais havendo a tratar, a presidente declarou",
        ],
        cabecalho + [
            "encerrada a sessão, e eu, Clara Modelo, secretária, lavrei a presente ata.",
        ],
    ]


def ce_colped() -> list[list[str]]:
    linhas = [
        "UNIVERSIDADE FEDERAL DO ESPÍRITO SANTO",
        "CENTRO DE EDUCAÇÃO - COLEGIADO DO CURSO DE PEDAGOGIA",
        "ATA DA 3ª REUNIÃO ORDINÁRIA DO COLEGIADO DO CURSO DE PEDAGOGIA, REALIZADA EM 4 DE MAIO",
        "DE 2022, ÀS TREZE HORAS E TRINTA MINUTOS, POR WEBCONFERÊNCIA, HAVENDO QUÓRUM.",
        "INFORMES:",
        "1. A coordenação informou o calendário fictício do semestre.",
        "2. Acolhimento fictício dos ingressantes em nova data.",
        "3. Reunião fictícia com os estudantes. O colegiado tomou ciência.",
        "PAUTA:",
        "1. Oferta fictícia de disciplinas do semestre. Aprovada por unanimidade.",
        "2. Plano de estágio sintético. Aprovado por unanimidade.",
        "3. Comissão fictícia de avaliação do curso. Aprovado por unanimidade.",
        "4. Pedido de aproveitamento de estudos de estudante fictício. Aprovado por unanimidade.",
        "Nada mais havendo a tratar, eu, Rosa Teste, secretária, lavrei a presente ata.",
    ]
    numeradas = []
    for indice, linha in enumerate(linhas, start=1):
        numeradas.append(linha)
        if indice % 5 == 0:
            numeradas.append(str(indice))
    return [numeradas]


def pagina_escaneada(destino: Path) -> None:
    rascunho = fitz.open()
    pagina = rascunho.new_page(width=A4.width, height=A4.height)
    y = 80
    for linha in ["UNIVERSIDADE FEDERAL DO ESPÍRITO SANTO", "Câmara Departamental de Ciências Fictícias",
                  "INFORME 1: comunicado sintético da chefia."]:
        pagina.insert_text((60, y), linha, fontname="helv", fontsize=16)
        y += 28
    imagem = pagina.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
    documento = fitz.open()
    documento.new_page(width=A4.width, height=A4.height).insert_image(A4, pixmap=imagem)
    documento.save(destino, garbage=4, deflate=True)


def texto_vetorizado(destino: Path) -> None:
    rascunho = fitz.open()
    pagina = rascunho.new_page(width=A4.width, height=A4.height)
    y = 80
    for linha in ["CONSELHO DEPARTAMENTAL", "Centro Universitário Norte do Espírito Santo", "São Mateus, ES"]:
        pagina.insert_text((60, y), linha, fontname="helv", fontsize=16)
        y += 28
    svg = pagina.get_svg_image(text_as_path=True)
    convertido = fitz.open("svg", svg.encode("utf-8")).convert_to_pdf()
    fitz.open("pdf", convertido).save(destino, garbage=4, deflate=True)


def main() -> None:
    fonte = sys.argv[1] if len(sys.argv) > 1 else FONTE_PADRAO
    amostras = AQUI / "atas_sample"
    a, b = amostras / "TIPO_A__Camara_Departamental", amostras / "TIPO_B__Conselho_Departamental_do_Centro"
    textos = {
        a / "CCENS_DB" / "ata_da_1a_reuniao_ordinaria_-_db_ccens_04-02-2025.docx.pdf": ccens_db(),
        a / "CCENS_DC" / "ata_da_01a_reuniao_de_carater_ordinario_dc_29_01_2025.docx.pdf": ccens_dc(),
        a / "CCENS_DC" / "ata_da_08a_reuniao_de_carater_ordinario_dc_27_06_2025.docx.pdf": ccens_dc_2_paginas(),
        b / "CAR" / "ata_05_02_2025.pdf": car(),
        b / "CCAE" / "1_ata_sessao_ordinaria_do_dia_28_de_janeiro_2025.pdf": ccae(),
        b / "CT" / "10-2025.pdf": ct(),
        amostras / "TIPO_C__Camara_Local_Tematica" / "CCHN_CamaraLocal_Graduacao"
        / "2020.08.17_-_ata_1a_ordinaria_camara_local.pdf": cchn_camara_local(),
        amostras / "TIPO_D__Colegiado_de_Curso" / "CE_Colegiado_Pedagogia"
        / "ata_da_3a_reuniao_ordinaria_colped.pdf": ce_colped(),
    }
    for destino, paginas in textos.items():
        _pdf_de_texto(destino, paginas, fonte)
    pagina_escaneada(AQUI / "ocr" / "dcab_pagina_escaneada.pdf")
    texto_vetorizado(AQUI / "ocr" / "ceunes_texto_vetorizado.pdf")


if __name__ == "__main__":
    main()
