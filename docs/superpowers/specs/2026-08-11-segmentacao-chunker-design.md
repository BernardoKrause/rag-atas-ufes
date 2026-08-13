# Parte 3 — Segmentação Estrutural (Chunker)

> Status: **aprovado, pronto para `writing-plans`** — self-review feito, risco da seção 4 investigado empiricamente contra o corpus real e resolvido, documento aprovado pelo usuário em 2026-08-12. Não reabrir as decisões já tomadas abaixo sem motivo novo.

## Contexto

Parte 2 (ingestão: `collector.py`+`extractor.py`+`cleaner.py`) já está mergeada em `main` (PR #2 + fix #3 de CENTRO_CAMPUS). Cada `Documento` tem `texto_limpo`: o texto completo da ata, já extraído e anonimizado (PII substituída por tokens determinísticos via HMAC).

Parte 3, pelo plano mestre (`Plano de Implementação — Graph-RAG Atas UFES.md`, no vault Obsidian — ver memória `reference-obsidian-vault-plan`): dividir cada ata em unidades de segmentação com sentido próprio (item de pauta, informe, deliberação, encaminhamento), com ID canônico compartilhado entre Postgres/Qdrant/Neo4j nas partes seguintes.

A ficha de campos do item de pauta está definida em `analise_estrutural_atas_ufes.md` §7 (ver decisão de escopo abaixo — só uma parte desses campos entra nesta Parte).

## 1. Visão geral / Arquitetura — APROVADO

Novo módulo `app/ingestion/segmentador.py`, com entrypoint próprio (`python -m app.ingestion.segmentador`), **desacoplado** do `pipeline.py` (roda depois, como um passo separado). Lê `Documento`s já persistidos no Postgres, gera `ItemPauta`s. Idempotente por `documento_id` (upsert/replace dos itens daquele documento a cada rerun).

**Por que desacoplado:** iterar na regex de segmentação não deve exigir rodar o NER real (lento, modelo de verdade) de novo a cada ajuste — só reprocessa a segmentação sobre o `texto_limpo` já persistido.

Fluxo: `Documento.texto_limpo` → detectar seções (EXPEDIENTE, ORDEM DO DIA, PAUTA, INFORME(S), COMUNICAD(O/ÇÃO/ÕES), PALAVRA LIVRE, EXCLUSÃO DE PAUTA) → dentro de cada seção, detectar itens pelo padrão de numeração do variant → por item, aplicar overflow-split (tamanho+overlap) se ultrapassar o limite → persistir `ItemPauta`.

**Gap técnico reaberto (página de origem):** `extrair_texto_bruto` (Parte 2) hoje junta as páginas do PDF com `"\n".join(...)`, perdendo a fronteira de página. Decisão: incluir rastreamento de página **já nesta Parte** (não adiar pra Parte 4).

- `extrair_texto_bruto` passa a retornar também a lista de offsets de início de cada página.
- Nova coluna `Documento.paginas_offsets` (JSON de inteiros, **nullable** — nulo nos documentos já ingeridos até reprocessados). Adicionada num novo commit dentro da branch da Parte 3 (não reabre o PR já mergeado da Parte 2, só estende o schema com uma migration nova).
- O texto em si (`texto_limpo`) **não** ganha nenhum marcador — fica limpo pra embeddings depois; os offsets ficam numa coluna à parte, sem tocar a lógica de janelamento do NER em `cleaner.py`.
- Os 357 documentos reais já ingeridos precisam de um rerun do `pipeline.py` (idempotente, sem duplicar) pra preencher essa coluna antes do segmentador rodar sobre eles — passo de verificação a incluir no "Como testar" do PR.

## 2. Modelo de dados — APROVADO

Nova tabela `itens_pauta`:

| Campo | Tipo | Nota |
|---|---|---|
| `id` | Integer PK autoincrement | |
| `documento_id` | FK → `documentos.id_documento` | |
| `item_id_canonico` | String, unique | determinístico: `f"{documento_id}_{secao_slug}_{numero_item}"` (+ sufixo de fragmento se dividido por overflow) — chave de correlação nas Partes 4/5 |
| `secao` | String | ORDEM DO DIA, PAUTA, INFORMES, EXPEDIENTE, COMUNICADOS, PALAVRA LIVRE, EXCLUSÃO DE PAUTA |
| `numero_item` | String (não int — alguns formatos não são puramente numéricos) | ex.: "2.1", "01", "3.2" |
| `fragmento_indice` | Integer, default 0 | 0 = item inteiro/primeiro fragmento; >0 = fragmentos subsequentes do overflow-split |
| `texto` | Text | o trecho do item (ou do fragmento) |
| `pagina_inicio` / `pagina_fim` | Integer, nullable | nullable pros documentos ainda não reprocessados com `paginas_offsets` |
| `criado_em` | DateTime | |

`UniqueConstraint(documento_id, secao, numero_item, fragmento_indice)`.

**Nota sobre o ID canônico e Qdrant:** Qdrant exige UUID ou inteiro como point ID nativo — uma string legível tipo `"233_PAUTA_2.1"` não serve como point ID lá, só como payload/propriedade. Decisão: `item_id_canonico` é a chave lógica de correlação (string determinística) armazenada como coluna/propriedade nos 3 bancos; Qdrant deriva seu point ID nativo via `uuid5(item_id_canonico)` quando a Parte 5 for implementada — não resolve o formato exato agora, só garante que a chave lógica funciona pros três.

**Fora de escopo nesta tabela (decisão de escopo — ver seção 3):** `assunto`, `tipo_desfecho`, `resultado_votacao`, `encaminhamento`, `resolucao_emitida`, `numero_processo`, `departamento_origem` — do §7 do `analise_estrutural_atas_ufes.md`. Não entram agora; Parte 4 os deriva do `texto` já segmentado.

## 3. Escopo dos campos — APROVADO

Só fronteiras + texto bruto: `numero_item`, `secao`, `texto` (trecho do item), `pagina_inicio`/`pagina_fim` — os campos estruturais que definem a fronteira e o ID canônico. Os campos de conteúdo semântico (assunto, desfecho, votação, encaminhamento, resolução, processo, departamento_origem) ficam nulos/fora da tabela nesta Parte, extraídos de verdade na Parte 4 a partir do `texto` já segmentado. Motivo: evita duplicar lógica de regex/NER entre Partes 3 e 4.

## 4. Estratégia de parsing — APROVADO (Abordagem A)

Duas fases:

1. **Detecção de seção** (compartilhada entre todos os variants): regex sobre o vocabulário limitado e comum de nomes de seção (confirmado pela matriz comparativa do `analise_estrutural_atas_ufes.md` — os nomes de seção se repetem entre variants, só a numeração de item varia).
2. **Detecção de item dentro da seção** (por variant): tabela de configuração dict-driven, chave `(tipo_orgao, centro)` → padrão de numeração de item (ex.: subnumeração pontilhada `\d+\.\d+` pros Tipos A/C/D, `\d{2}\)` pro Tipo B2/CAR, etc.) — mesmo estilo já usado no projeto (`CENTRO_CAMPUS` em `extractor.py`).

Rejeitadas: regex único de passada única sem ancorar em seção primeiro (risco de falso positivo com números soltos no meio de pareceres/processos SIPAC); função dedicada e independente por variant (duplicaria a lógica de detecção de seção, que a matriz comparativa mostra ser compartilhada).

**Risco investigado e resolvido (verificação empírica contra o corpus real, 2026-08-12):** a matriz comparativa só documenta estrutura detalhada pros 3 variants nomeados de Tipo B (B1/CT, B2/CAR, B3/CCAE). Os demais centros de Tipo B foram checados contra os 357 documentos já ingeridos (Postgres, 2 amostras por centro):

- **CE e CCHN** (Conselho Departamental): usam subnumeração pontilhada (`\d+\.\d+`, ex.: `01.01.`, `3.04`) — o **mesmo padrão já previsto pros Tipos A/C/D**. As seções aparecem com número inline no próprio nome ("01. Apreciação de atas/relatórios", "02. Comunicações", "3. PAUTA"), mas o vocabulário de nomes de seção é o mesmo já mapeado. **Não precisam de entrada nova na tabela de config** — reaproveitam o padrão pontilhado existente.
- **CEFD**: genuinamente diferente, confirmado em 2 documentos. Numeração de item por colchete (`[1]`, `[2]`, `[3]`...), não pontilhada. Vocabulário de seção com nomes fora da lista documentada: `EM PAUTA` (variante de "PAUTA") e `PROCESSOS/PROJETOS` (seção nova, sem equivalente em nenhum dos 6 variants mapeados). **Precisa de entrada nova**: padrão de numeração `\[\d+\]` na tabela de config pra `(B, CEFD)`, mais extensão do vocabulário de detecção de seção pra reconhecer `EM PAUTA` (alias de PAUTA) e `PROCESSOS/PROJETOS` (nova seção).

CCE não foi verificado (sem documentos Tipo B desse centro nos 357 já ingeridos até o momento) — se aparecer no rerun de reprocessamento, tratar como os demais: cai no fallback `ValueError` até checagem manual, mesmo padrão de segurança já aprovado para variant desconhecido.

## 5. Overflow-split e casos de borda — APROVADO

**Limite de tamanho:** heurístico por caracteres, não o tokenizer real do modelo de embedding (ainda não escolhido — isso é decisão da Parte 5). Constantes nomeadas, mesmo estilo de `JANELA_ABERTURA = 3000` já existente em `extractor.py`: `TAMANHO_MAX_FRAGMENTO = 3000` caracteres, `SOBREPOSICAO_FRAGMENTO = 300` (10%).

**Casos de borda:**
- **EXCLUSÃO DE PAUTA** (subseção do Tipo C): vira sua própria `secao`, não fica dentro de "EXPEDIENTE".
- **Fórmula de encerramento + assinaturas**: não capturada por nenhum padrão de seção conhecido — fica de fora naturalmente, sem "pega-tudo" no final.
- **Variant desconhecido** (`tipo_orgao`+`centro` sem entrada na tabela de config): erro explícito (`ValueError`), mesmo padrão do `mapear_campus` — não falha silenciosamente.
- **Seção sem itens numerados detectáveis** (ex. PALAVRA LIVRE só com texto livre): seção pulada, nenhum `ItemPauta` criado.

## 6. Testes — APROVADO

Reaproveitar as 6 fixtures reais já commitadas (`backend/tests/fixtures/atas_sample/`, uma por variante A/B1/B2/B3/C/D) — contar manualmente os itens/seções esperados (lendo o PDF) como *ground truth* fixo nos testes, mesmo padrão "testado contra dado real, sem mock" do resto do projeto. Mais um caso sintético só pra exercitar o overflow-split (não ocorre nas 6 fixtures atuais).

## Pendências antes de seguir pra `writing-plans`

1. ~~Self-review da spec (placeholders, contradições, escopo, ambiguidade)~~ — feito em 2026-08-12, sem problemas bloqueantes.
2. ~~Aprovação final do documento escrito pelo usuário~~ — aprovado em 2026-08-12.
3. ~~Risco da seção 4 (centros de Tipo B sem variant documentada)~~ — investigado empiricamente contra o corpus real (ver seção 4): CE/CCHN reaproveitam o padrão pontilhado existente; CEFD precisa de entrada nova (`[\d+]` + vocabulário `EM PAUTA`/`PROCESSOS/PROJETOS`); CCE fica pendente de verificação futura (sem amostra Tipo B no corpus atual), coberto pelo fallback `ValueError`.

Todas as pendências resolvidas — pronto para `writing-plans`.
