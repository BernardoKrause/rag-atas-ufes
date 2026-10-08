# Validação manual da extração (Parte 10)

O TCC1 exige uma validação manual da extração de entidades e relações antes que o grafo alimente a avaliação. A amostra é estratificada pelos quatro tipos estruturais (A, B, C e D) em proporção equivalente. Cada erro é registrado com uma categoria, o trecho de origem e a regra que precisa ser ajustada.

Este documento descreve como a validação foi feita sobre o corpus completo, os resultados obtidos e as limitações que permanecem.

## Corpus processado

O processamento completo é feito com `python -m app.ingestion.completa`, que roda em sequência a extração, a anonimização, a segmentação, o enriquecimento, a indexação e o grafo.

| | Valor |
|---|---|
| Atas | 357 |
| Atas com páginas extraídas por OCR | 16 (12 do CEUNES_DCAB, 3 do Conselho do CEUNES, 1 anexo do CCENS_DG) |
| Itens de pauta lógicos / linhas com fragmentos | 3.362 / 3.588 |
| Janelas no Qdrant | 8.947 |
| Desfecho por item lógico | Aprovado 2.254, sem desfecho 955, Retirado 141, Reprovado 9, Encaminhado 3 |
| Itens com ato emitido / departamento de origem / encaminhamento | 67 / 113 / 32 |
| Grafo | 357 atas, 2.407 deliberações, 32 encaminhamentos, 1.588 processos, 3.053 assuntos, 362 relações `trata_do_mesmo_assunto` |
| Ligaduras ou glifos trocados no texto | 0 |

### OCR

As atas do CEUNES_DCAB são fotos ou escaneamentos da ata impressa. As três primeiras sessões de 2024 do Conselho do CEUNES foram geradas pelo "Print To PDF" com o texto convertido em desenho. Nenhuma das duas tem camada de texto. A extração aplica OCR (Tesseract, `por`) apenas às páginas sem texto nativo e registra essas páginas em `documentos.paginas_ocr`.

Sem o OCR, o DCAB inteiro ficaria fora do corpus e a cobertura cairia de 16 para 15 departamentos.

### Atas sem item de pauta (8)

| id | órgão | classe | evidência |
|---|---|---|---|
| 1848 | CEUNES | sem deliberação | abertura seguida de "Nada mais havendo a tratar" (OCR) |
| 1908 | CCAE_DEAL | sem deliberação | convocação por formulário online |
| 1921 | CCAE_DPV | sem deliberação | sessão sem quórum |
| 1923 | CCAE_DPV | sem deliberação | sessão sem quórum |
| 1656 | CCENS_DB | limitação do detector | numeração inconsistente ("1. Ordem do dia. 3.1 ...") |
| 1661 | CCENS_DB | limitação do detector | consulta por e-mail com os itens 1.1/2.1/2.2 escritos no meio do texto |
| 1874 | CCAE_DER | limitação do detector | item único no meio do texto: "assunto: (...) 1.1 Eleição de Chefe" |
| 1945 | CCE | limitação do detector | "Pauta: Assuntos Gerais", sem itens numerados |

As três atas do CEFD que antes ficavam sem item (pauta narrativa "EM PAUTA: ... COMUNICAÇÕES:") passaram a ser segmentadas.

## Protocolo

- **Amostra:** gerada por `python -m scripts.validacao_manual_grafo`. São 15 itens por tipo estrutural, distribuídos em rodízio entre as variantes (tipo × centro) para não concentrar a amostra no órgão com mais itens. A amostra inclui ainda estratos suplementares de campos raros: até 8 itens com `ato_emitido`, até 8 com `departamento_origem` e todos os itens com desfecho Reprovado ou Adiado.
- **Campos conferidos contra a ata:** limites do item, assunto, desfecho, resultado da votação, encaminhamento, ato emitido, departamento de origem, processos e itens ligados por "mesmo assunto".
- **Categorias de erro:** as do TCC1 (órgão incorreto, processo não reconhecido, deliberação sem desfecho identificado, relação espúria entre assuntos), mais as categorias que surgiram durante a revisão: deliberação espúria, segmentação incorreta, resultado da votação incorreto, encaminhamento não extraído ou espúrio, departamento de origem incorreto e anonimização parcial.
- **Correção:** os erros com causa raiz comum são corrigidos com teste (TDD) e o corpus é reprocessado. Os erros isolados ficam registrados como limitação. A regra só é generalizada quando há causa compartilhada.
- **Revisão:** a pré-revisão item a item foi feita com assistência do Claude Code, comparando cada campo com o texto completo do item. O resultado está nas colunas `correto`, `categoria_erro` e `observacao` das planilhas em `docs/validacao/`. A conferência final cabe ao autor.

## Rodada 1: amostra de calibração (semente 42, 79 itens)

A primeira amostra serviu para encontrar os erros e orientar as correções. Ela foi medida duas vezes: antes das correções e depois delas.

| Tipo | Corretos antes | Corretos depois |
|---|---|---|
| A (15) | 12 | 14 |
| B (34) | 25 (+3 parciais) | 33 |
| C (15) | 14 | 14 (1 parcial) |
| D (15) | 11 | 14 |
| **Total** | **62 (78%)** | **75 (95%)** |

Os 95% medem se os erros encontrados foram corrigidos. Eles não medem a acurácia em itens não vistos, porque as regras foram ajustadas sobre esses mesmos 79 itens.

Erros da medição inicial (14 errados e 3 parciais):

| Categoria | Qtde | Causa raiz | Ajuste |
|---|---|---|---|
| Deliberação espúria | 8 | palavra-chave de desfecho buscada em qualquer parte do texto ("os alunos foram *reprovados*", "*ainda não foi aprovada*", "precisou ser *adiado*") | o desfecho só vale em frase com marca de votação, em frase que começa pela palavra-chave ou em "retirado de pauta" |
| Resultado da votação incorreto | 1 + 3 parciais | frase cortada em abreviação ("Dr."), sem fim delimitado, ou cortada na fronteira entre fragmentos | delimitação de frase com abreviações e aspas; enriquecimento do texto completo do item fragmentado |
| Segmentação incorreta | 2 | o último item absorvia o encerramento, as assinaturas e os protocolos de assinatura digital | cada item termina em "Nada mais havendo a tratar". Os itens que começam depois de um encerramento são mantidos, porque os extratos de ata do CCE (docs 1976 e 1988) repetem o fecho a cada página |
| Deliberação sem desfecho identificado | 1 | fragmentos de item longo eram enriquecidos isoladamente | enriquecimento do texto completo do item |
| Encaminhamento não extraído | 1 | o campo nunca era extraído (vazio nos 3.716 itens) | extração conservadora: "encaminhamento: ..." ou "encaminhamento à/ao/para ..." em item com desfecho |
| Anonimização parcial | 1 | o NER cortou um sobrenome ("PESSOA_165708ísio") | limitação (isolado) |

## Rodada 2: amostra independente (semente 2026, 76 itens)

A segunda amostra exclui os itens da rodada 1 e foi medida **antes** de qualquer ajuste. **É este o número reportado para a extração.**

| Tipo | Corretos | Parciais | Errados |
|---|---|---|---|
| A (15) | 14 | 1 | 0 |
| B (31) | 26 | 1 | 4 |
| C (15) | 10 | 2 | 3 |
| D (15) | 14 | 0 | 1 |
| **Total (76)** | **64 (84%)** | **4** | **8** |

Contando os parciais como acertos, são 68 de 76 (89%).

Os campos com melhor desempenho foram:
- os atos emitidos do CCAE (9 de 9);
- o departamento de origem do CT (7 de 8);
- os desfechos e as votações do CT e do CCAE;
- o item vindo de OCR;
- as relações entre atas.

As relações entre atas conferidas incluem um processo retirado de pauta numa reunião do CT e reapresentado na seguinte, e a abertura de um concurso no CCHN ligada à recomposição da banca meses depois.

| Categoria | Qtde | Itens | Tratamento |
|---|---|---|---|
| Segmentação incorreta | 5 | enumeração interna de parecer do CAR lida como item (2); seção seguinte absorvida (CCAE e CCHN); encerramento sem "Nada mais havendo"; item que engoliu os seguintes por cabeçalho vazado (Pedagogia) | CAR corrigido; os demais são limitação |
| Deliberação sem desfecho identificado | 3 | "baixado de pauta" (2); "foi discutida e aprovada" sem palavra de votação (1) | corrigidos |
| Deliberação incompleta | 1 | item com várias deliberações recebe só a última | limitação do modelo (um desfecho por item) |
| Departamento de origem incorreto | 1 | departamento tirado de uma lista de rateio de orçamento | limitação (isolado) |
| Encaminhamento espúrio / não extraído | 2 | trecho normativo; encaminhamento implícito | limitação |

### Correções aplicadas depois da medição (não remedidas na amostra)

| Ajuste | Efeito no corpus |
|---|---|
| "baixado de pauta" passa a ser Retirado, só em seções deliberativas | +7 Retirado |
| Aprovação sem palavra de votação ("discutida e aprovada", "sendo aprovado pelos presentes", "após discussão") aceita só em seções deliberativas e só quando não há outra ocorrência válida no item | +15 Aprovado (2 falsos positivos: 1953_PAUTA_23, 1959_PAUTA_20) |
| Enumeração interna do CAR: o marcador "N)" só abre item seguido de letra maiúscula ou de "proc" | −16 marcadores espúrios |
| Rejeição em frase de votação ("rejeitado por unanimidade", "não foi aprovada por maioria", "Decisão: Não aprovado(a)") passa a ser Reprovado | Reprovado de 0 para 9 |
| A deliberação é criada só no primeiro fragmento do item; os demais fragmentos se ligam a ela | 185 nós `Deliberação` duplicados a menos; fragmentos do mesmo item deixam de se ligar como "mesmo assunto" |

Depois da regra de rejeição, 4 itens com rejeição explícita continuam como Aprovado: 1667_ORDEM_DO_DIA_3.2, 1750_PAUTA_04.01, 1964_PAUTA_9 e 1732_PAUTA_3.22. Em todos eles há uma aprovação válida mais adiante no mesmo item, e a regra usa a última ocorrência válida.

## Limitações conhecidas

- **Um desfecho por item.** Itens com várias deliberações (por exemplo, uma proposta aprovada e um processo retirado no mesmo ponto) ficam só com a última.
- **Encaminhamento.** A extração é conservadora e tem baixa cobertura: 32 itens. Dos 31 conferidos, cerca de 24 estão corretos. Há casos procedimentais (1684, 1707), normativos (1770, 1778), um trecho citado de outra ata (1983) e dois truncados (1780_PAUTA_3 em "“1." e 1780_PAUTA_2_D1 em "Ofício no").
- **Assunto.** O campo guarda o corpo do item até a frase da votação, não um título curto. A relação "mesmo assunto" se apoia principalmente no processo compartilhado.
- **Segmentação.** Ainda há:
  - cabeçalhos e rodapés de página vazados no meio do texto em alguns modelos ("Emissão: ... Página 2/4", cabeçalho institucional do Colegiado de Pedagogia, numeração de margem do CCAE);
  - encerramentos sem a fórmula "Nada mais havendo a tratar";
  - seções seguintes absorvidas em variantes sem seção explícita;
  - 4 atas com formato único sem nenhum item.
- **Regras de frase.** Faltam abreviações raras (Exmo., pág., inc.). "maioria" conta como marca de votação, o que aceita frases como "a maioria dos alunos foi aprovada". Uma frase com negação e aprovação juntas é julgada como um todo.
- **OCR.**
  - A qualidade do OCR depende do escaneamento. Nos 2 itens de OCR amostrados (um por rodada) não houve erro atribuído a ele. Fora da amostra, o OCR da tabela do DCAB inseria ruído entre o rótulo e o desfecho ("Decisão: | Aprovado(a)", "Decisão; Aprovado(a)") e deixava 8 itens sem desfecho. O extrator do CT passou a tolerar esse ruído.
  - Páginas em branco que contenham algum desenho, como bordas, também passam pelo OCR.
  - A ingestão completa exige o Tesseract instalado.
- **Anonimização.** O NER pode cortar sobrenomes. Há um número de documento avulso (formato 028498/25-52, um único caso no corpus) que não segue o padrão de processo e não é anonimizado.
- **Atas anexadas.** O doc 1709 (CCENS_DQF, reunião de 05/05/2025) traz anexada a ata da 21ª sessão ordinária de 15/12/2022. Os itens 2.1 a 3.8 dessa ata anexada são indexados com os metadados da reunião de 2025.

## Planilhas

As planilhas ficam em `docs/validacao/`:
- `amostra1_pre_revisao.csv`: rodada 1, valores e pré-revisão antes das correções;
- `amostra1_revalidacao.csv`: rodada 1, revalidada depois das correções A, B e C;
- `amostra2_independente.csv`: rodada 2, a medição reportada.
