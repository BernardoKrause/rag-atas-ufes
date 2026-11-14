import csv
import json
import re

D = "/Users/bk/Documents/Projects/RAG ATAS UFES - TCC/deploy_bernardo/amostra_personas_40"
CSV = "docs/avaliacao/teste_manual.csv"
PRE = "docs/avaliacao/rastreios/v3/prerodada_40_checagem.jsonl"

C = {
    "3": ("correta", "", "", "A presidência passou para a chefe do departamento, e o professor anterior continua como membro; aprovado por unanimidade. É o que a pergunta pede (quem), com data e item certos."),
    "4": ("correta", "", "", "Indica o professor que se disponibilizou e foi aprovado por unanimidade (13/06/2024, pauta 3.3). A linha repete a votação."),
    "5": ("correta", "", "", "As datas de 10/07/2024 (ordem do dia 3.2) conferem com o gabarito. A resposta traz também o calendário de 11/04/2024 (item 3.6), cujo título na ata também diz semestre 2024/1 e que não está no gabarito. A afirmação tem apoio no trecho; possível lacuna do gabarito."),
    "6": ("correta", "", "", "22/11/2024 (ordem do dia 1.2) confere: representação estudantil em desacordo com o Regimento e o ponto volta a ser discutido. Traz também 06/11/2024 (definição das presidências, item 3.9) e 06/12/2024 (homologação final), ambos com apoio nos trechos. O rótulo da fonte [3] aponta o item 1.1, mas o texto é do item 3.9 (segmentação)."),
    "7": ("correta", "2/2", "", "As duas bancas de tese do gabarito (06/12/2024 por unanimidade; 13/03/2025 por maioria) estão certas. Ruído: três bancas de dissertação (13/02 e 27/02/2025), descritas corretamente como dissertação."),
    "8": ("correta", "", "", "Desfecho confere: a impugnação foi posta em votação e não aprovada, com um voto favorável (25/11/2011, item 11). Não explica quem pediu nem contra quem."),
    "9": ("parcial", "4/7", "", "Traz 4 das 7 atas do gabarito (23/04, 29/08 e 17/12/2014; 27/05/2015), todas aprovadas por unanimidade. Faltam 29/05/2012, 25/02/2014 e 27/06/2014 (recuperação, top 5). A descrição de 23/04/2014 confunde o trâmite: diz 'Conselho Departamental do Departamento de Física'."),
    "10": ("correta", "4/4", "", "As quatro retiradas de pauta do gabarito estão certas. Traz também 30/05/2011 (item 09), outra retirada de pauta do mesmo assunto que o gabarito não lista."),
    "11": ("correta", "", "", "Aprovado por unanimidade em 18/02/2025, item 3.2. A frase direta saiu como fragmento ('foi aprovado por unanimidade')."),
    "12": ("parcial", "1/2", "sim", "22/07/2025 confere (COM05207 turma VE1 não será ofertada). Falta 24/04/2025 (referências bibliográficas da disciplina, aprovado por unanimidade), que não entra no top 5."),
    "13": ("correta", "2/2", "sim", "As três ocorrências do gabarito estão certas: 24/04/2025 expediente 1.1 (inclusão, unanimidade), ordem do dia 3.6 (redução de 40 para 35 vagas, maioria) e 29/05/2025 comunicação 4.2. No mesmo dia, o item 3.6 aparece antes do 1.1. Traz também 10/07/2025 (projeto de ensino da disciplina), com apoio no trecho."),
    "14": ("correta", "", "", "Relatório aprovado por unanimidade em 30/05/2025, item 3.5."),
    "15": ("correta", "", "", "19/08/2024 (ordem do dia 3.3): disciplina distribuída entre professores, aprovado por unanimidade. Não diz o motivo (afastamento da docente). Ruído: monitorias de 20/05, bibliografia de 10/06 e inclusão de pauta de 19/08."),
    "16": ("correta", "", "", "27/02/2024 (item 2.11): relatório da III Semana Acadêmica de Matemática aprovado por unanimidade. Ruído: relatório de encargos (20/06), OBMEP (08/07) e OAMAT (08/08)."),
    "17": ("correta", "", "", "16/04/2024 (item 3.2): projeto aprovado pela maioria, como na ata. 08/08/2024 (OAMAT na planilha de carga horária) é desdobramento do mesmo projeto. A frase direta repete o evento."),
    "18": ("correta", "2/2", "", "27/03/2025: aprovados os planos inseridos e os faltantes ficam para 24/04, por unanimidade. 24/04/2025: aprovados os planos restantes. Traz também o prazo de 13/03 e a comunicação de 24/04 sobre a assinatura, com apoio nos trechos."),
    "19": ("correta", "2/2", "sim", "24/04/2025 (retificação da ata para incluir o programa de DQF05566) e 22/05/2025 (retificação: oferta no 2º período) conferem, em ordem. Ruído: DQF05605 (05/05/2025), descrita com o código certo."),
    "20": ("incorreta", "1/3", "", "Só 14/03/2023 é do gabarito; faltam 26/04/2022 e 28/03/2023. Os outros três afastamentos (01/02/2022, 31/01/2023, 14/02/2023) são do CCHN e aprovados, mas não estão no gabarito. Alucinação: a linha de 31/01/2023 expande CCHN como 'Conselho Científico-Habilitador de Nível Nacional'. A correção G não pega porque CCHN está no rótulo da fonte."),
    "21": ("parcial", "3/7", "", "Traz 3 das 7 atas do gabarito (01/02, 15/02 e 08/03/2022), todas aprovadas por unanimidade. Faltam 26/04/2022, 14/03, 28/03 e 11/04/2023 (recuperação, top 5)."),
    "22": ("correta", "", "", "15/03/2021: discussão da suspensão de turmas no SISU, pedido a ser submetido aos Conselhos Superiores e contato com a TAE. Imprecisão pequena: os participantes citados estavam na reunião com a Prograd, não nesta."),
    "23": ("incorreta", "3/3", "", "As três atas estão citadas, mas a linha de 17/08/2020 diz que as diretrizes foram aprovadas, quando a ata registra só a aprovação da consulta à Prograd (o 'Resultado da votação' anexado diz o certo e contradiz a frase). 21/09/2020 e 10/07/2021 conferem (diretrizes aprovadas por unanimidade)."),
    "24": ("correta", "", "", "Aprovado por unanimidade em 28/03/2025, item 04.14. Erro de digitação: 'unanidade'."),
    "25": ("correta", "2/2", "", "31/01/2025 e 30/05/2025 aprovados por unanimidade, como no gabarito. A frase direta saiu como fragmento."),
    "26": ("correta", "", "", "13/07/2022 (item 4.1): oferta 2022/2 aprovada à unanimidade. Ruído: oferta 2021/2 (06/09/2021) e uma ata de 2021 datada 03/05/2003 no corpus, com descrição que mistura dois assuntos do trecho."),
    "27": ("correta", "", "", "04/05/2022 (informe 3.4): acolhimento virtual e adiado. Traz também 07/03/2022 (palestras reprogramadas para 04/05 e 12/05), com apoio no trecho."),
    "28": ("correta", "", "", "15/02/2023 (item 3): licença aprovada por unanimidade após parecer. Ruído: outras licenças e afastamentos do CEFD; na linha [5] o 'Professor Dr.' da ata virou 'professora Drª' e o 'Resultado da votação' é o da leitura da ata. A frase direta é longa e mistura quatro casos."),
    "29": ("correta", "", "", "26/04/2023 (item 5): afastamento para pós-doutorado aprovado por unanimidade. Ruído: visita técnica de outra professora, mesma ata."),
    "30": ("correta", "2/2", "sim", "As duas inclusões de prestadores voluntários para ECH15737 (05/02 e 25/03/2024), por unanimidade e em ordem. Na v1 e na v2 era abstenção indevida."),
    "31": ("correta", "", "", "17/12/2025: relatório do VII ENCOMP aprovado por unanimidade após parecer da comissão."),
    "32": ("correta", "", "", "15/02/2023: aprovação ad referendum da chefia referendada. A descrição não diz explicitamente que a câmara referendou."),
    "33": ("correta", "", "", "26/02/2025: equivalências aprovadas por unanimidade conforme o Ofício 003/2025. Traz também a retificação de 23/04/2025 (Eng. de Petróleo), com apoio no trecho."),
    "34": ("correta", "", "", "23/04/2025 (item 6): retificação das equivalências de Eng. de Petróleo aprovada por unanimidade. Traz também 26/02/2025 (equivalências do DCN)."),
    "35": ("correta", "", "", "01/07/2024: parecer sobre o relatório do Imuniza Norte aprovado por unanimidade."),
    "36": ("correta", "", "", "26/09/2023: retificação da pauta 3 aprovada por unanimidade."),
    "37": ("parcial", "", "", "20/02/2025: diz que as atas de 21/11/2024, 19/12/2024 e 30/01/2025 foram aprovadas sem alteração, mas omite o centro do item: a ata de 07/11/2024 foi aprovada com o texto da eleição da chefia modificado. Ruído: aprovação de ata em 13/03/2025."),
    "38": ("correta", "", "", "27/03/2025: homologação do PS 13/2025 aprovada por unanimidade, com os aprovados em 1º e 2º. 13/03/2025 é o informe do resultado."),
    "39": ("correta", "", "", "22/08/2025: eleição do PPGEA homologada, com coordenador e adjunto."),
    "40": ("correta", "", "", "22/08/2025 (item 5): eleição homologada. A linha de 12/12/2025 é da coordenação de Eng. de Produção Noturno, mas a descrição não diz o curso e parece ser a do vespertino (enganoso por omissão)."),
}

perg = {r["n"]: r for r in csv.DictReader(open(f"{D}/perguntas.csv", encoding="utf-8-sig"), delimiter=";")}
links = dict(re.findall(r"^\| (\d+) \| \S+ \| \S \| (\S+) \|", open(f"{D}/links_portal.md", encoding="utf-8").read(), re.M))
pre = {str(json.loads(l)["n"]): json.loads(l) for l in open(PRE, encoding="utf-8")}

with open(CSV, "a", encoding="utf-8", newline="") as f:
    w = csv.writer(f, delimiter=";")
    for n in range(3, 41):
        n = str(n)
        p, r = perg[n], pre[n]["resposta"]
        classe, atas, ordem, just = C[n]
        texto = r["texto"].replace("\n", " / ")
        fontes = " | ".join(f"[{x['numero']}] {x['rotulo']} ({x['item_id_canonico']})" for x in r["fontes"])
        w.writerow([n, p["consulta_id"], p["setor"], p["situacao"], p["persona_tipo"], "original", links[n],
                    "2026-11-12", p["pergunta"], texto, fontes, "sim" if r["abstencao"] else "nao", classe, "sim",
                    atas, ordem, "sim", just, "", "v3"])
