## Recuperação

| Config | Categoria | n | P@5 | R@5 | MRR | nDCG@5 |
|---|---|---|---|---|---|---|
| A | intra_exata | 1 | 0,200 | 1,000 | 1,000 | 1,000 |
| A | intra_reformulada | 1 | 0,000 | 0,000 | 0,000 | 0,000 |
| A | inter_atas | 1 | 0,000 | 0,000 | 0,000 | 0,000 |
| A | longitudinal | 1 | 0,200 | 0,250 | 0,500 | 0,246 |
| A | todas | 4 | 0,100 | 0,312 | 0,375 | 0,312 |
| B | intra_exata | 1 | 0,200 | 1,000 | 1,000 | 1,000 |
| B | intra_reformulada | 1 | 0,200 | 1,000 | 0,200 | 0,387 |
| B | inter_atas | 1 | 0,200 | 0,333 | 0,200 | 0,182 |
| B | longitudinal | 1 | 0,400 | 0,500 | 1,000 | 0,559 |
| B | todas | 4 | 0,250 | 0,708 | 0,600 | 0,532 |
| C | intra_exata | 1 | 0,200 | 1,000 | 1,000 | 1,000 |
| C | intra_reformulada | 1 | 0,000 | 0,000 | 0,000 | 0,000 |
| C | inter_atas | 1 | 0,000 | 0,000 | 0,000 | 0,000 |
| C | longitudinal | 1 | 0,200 | 0,250 | 1,000 | 0,390 |
| C | todas | 4 | 0,100 | 0,312 | 0,500 | 0,348 |
| D | intra_exata | 1 | 0,200 | 1,000 | 1,000 | 1,000 |
| D | intra_reformulada | 1 | 0,200 | 1,000 | 1,000 | 1,000 |
| D | inter_atas | 1 | 0,400 | 0,667 | 0,500 | 0,478 |
| D | longitudinal | 1 | 0,600 | 0,750 | 1,000 | 0,832 |
| D | todas | 4 | 0,350 | 0,854 | 0,875 | 0,827 |

## Geração (RAGAS)

Média por métrica, com o número de respostas avaliadas entre parênteses.

| Config | Categoria | faithfulness | answer_relevancy | context_precision | context_recall |
|---|---|---|---|---|---|
| A | intra_exata | 1,000 (1) | 0,876 (1) | 1,000 (1) | 1,000 (1) |
| A | intra_reformulada | – (0) | – (0) | 0,000 (1) | 0,000 (1) |
| A | inter_atas | – (0) | – (0) | 0,000 (1) | 0,000 (1) |
| A | longitudinal | 1,000 (1) | 0,939 (1) | 0,500 (1) | 0,500 (1) |
| A | todas | 1,000 (2) | 0,908 (2) | 0,375 (4) | 0,375 (4) |
| B | intra_exata | 1,000 (1) | 0,876 (1) | 1,000 (1) | 1,000 (1) |
| B | intra_reformulada | 1,000 (1) | 0,955 (1) | 0,200 (1) | 0,667 (1) |
| B | inter_atas | – (0) | – (0) | 0,000 (1) | 0,000 (1) |
| B | longitudinal | – (0) | – (0) | 1,000 (1) | 0,500 (1) |
| B | todas | 1,000 (2) | 0,916 (2) | 0,550 (4) | 0,542 (4) |

## Abstenção

| Config | Correta | Indevida |
|---|---|---|
| A | 1,00 | 0,50 |
| B | 1,00 | 0,50 |

Erros de geração: 0. Respostas truncadas: 0. Métricas RAGAS sem valor: 0.

## Custo

Gerador (qwen2.5:7b): 57455 tokens de entrada e 411 de saída; US$ 0,00 (modelo local).

Juiz (qwen2.5:14b): 132490 tokens de entrada e 7168 de saída; US$ 0,00 (modelo local).

Total: US$ 0,00.
