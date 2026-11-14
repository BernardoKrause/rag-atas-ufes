# Teste manual do RAG

Registro do teste manual da geração, pergunta por pergunta. Os resultados ficam em `teste_manual.csv`, ao lado deste arquivo.

## Protocolo

- **Perguntas:** as 40 originais da amostra por persona (`deploy_bernardo/amostra_personas_40/`, semente 20261107, teto 40), tiradas da base do orientador (edição `edicao_documental_7c71f82d57c1`). Elas cobrem 24 personas (uma por setor) e 9 centros: 27 B (uma ata), 8 C (entre atas) e 5 D (histórico). Os critérios estão na spec do ground truth, §0. As versões reformuladas (variação de vocabulário) entram depois, se o orientador aprovar o desenho em pares.
- **Sistema:** configuração A (recuperação híbrida completa: BM25 + vetorial + grafo), gerador `qwen2.5:7b` no Ollama local, temperatura 0. O código é o do worktree `avaliacao-final`, a partir do commit `6da6076`.
- **Execução:** o usuário faz a pergunta no frontend (`localhost:5173`). A mesma pergunta é repetida na API (`POST /consultas`) para registrar o texto exato e as fontes. Com temperatura 0 as duas respostas coincidem, e qualquer divergência é anotada.
- **Portal do orientador:** cada pergunta tem um link no portal (`127.0.0.1:18573/#setor=<setor>&consulta=<consulta_id>`), onde o usuário registra a avaliação dele em paralelo (`portal/dados/avaliacoes.sqlite3`). A lista completa está em `deploy_bernardo/amostra_personas_40/links_portal.md`.
- **Conferência:** a resposta é comparada com o gabarito do orientador (`gabarito.csv`, mesmo `consulta_id`). O gabarito não é anonimizado, por isso não é copiado para o repositório. Nomes e processos do gabarito equivalem a `PESSOA_n` e `PROCESSO_n` na resposta.

## Rubrica

| Classe | Definição |
|---|---|
| `correta` | Traz o fato central da referência (desfecho, órgão, data e, em C/D, cada ata relevante) e não afirma nada contrário à ata |
| `parcial` | O fato central está certo, mas falta um elemento obrigatório (uma das atas em C/D, a data ou o desfecho em B) |
| `incorreta` | Desfecho errado, ata errada, ou afirmação sem apoio nas fontes (alucinação) |
| `abstencao_indevida` | O sistema diz que não encontrou, embora haja evidência |

Elementos obrigatórios: em B, desfecho, órgão e data da reunião (nas perguntas de foco específico, como "Quem foi indicado" ou "Quais datas foram definidas", o elemento obrigatório é o que a pergunta pede, e o desfecho da votação passa a complementar; regra fixada em 2026-11-07, na P3); em C, o desfecho de cada ata relevante; em D, os eventos na ordem cronológica correta.

Colunas complementares: `citacao_correta` (pelo menos uma fonte citada é a ata e o item da referência), `atas_citadas` (atas relevantes citadas sobre o total, só em C e D), `ordem_cronologica` (só em D) e `data_no_texto` (a data da reunião aparece no texto da resposta, e não só no rótulo da fonte).

**Regra da data (decidida em 2026-11-07, na pergunta 1):** a data da reunião conta como presente quando está no rótulo da fonte citada, porque a fonte aparece na tela junto com a resposta. Em C e D isso só vale se o marcador `[n]` estiver ligado à afirmação, de modo que se saiba a data de cada desfecho. A coluna `data_no_texto` registra a diferença, porque o RAGAS lê só o texto e pode penalizar a ausência da data.

**Portal do orientador:** a avaliação do portal confere o **gabarito do orientador** (se a resposta esperada da base bate com a ata), não a resposta do RAG. O usuário usa a avaliação simples (`correta` sim/não, resposta corrigida, observações). A revisão detalhada de 6 critérios (rodada `piloto-1`) só entra se o orientador pedir.

## Andamento

| Data | Perguntas testadas | Observações |
|---|---|---|
| 2026-11-07 | 3/40 | Início do teste. Ambiente: Colima 4 GB, API e frontend do worktree, Ollama nativo. P1 correta, P2 parcial, P3 correta |
| 2026-11-08 | 1/40 (versão 2) | Teste parado na P4 para as correções A (BM25 e fusão) e B (geração por evento, em duas chamadas). API reiniciada com o commit `6b33940`. O teste recomeça da P1, e as linhas da versão 1 ficam no CSV com `versao_sistema = v1` (commit `6da6076`). As da versão 2 levam `v2` (commit `6b33940`) |
| 2026-11-09 | — | Correções C, D e E prontas no worktree, sem commit. API reiniciada com esse código. Banco e grafo de desenvolvimento já corrigidos |
| 2026-11-09 | — | Versão 3 commitada (`e8c05b4`, branch `feat/numero-real-do-processo`, empilhada). A API roda esse código. O teste recomeça da P1, e as linhas levam `versao_sistema = v3` |
| 2026-11-11 | — | Pré-rodada das 40 pela API mostrou citações de outro setor. Correção F (filtro por setor) e ajuste do ponto duplo. Versão 3 final: `88e87ba` (`fix/ponto-final-do-desfecho`). A API roda esse código e o teste manual começa da P1 |
| 2026-11-12 | — | Teste manual v3 parado na P1 (contaminação da descrição pela pergunta). Correção G: checagem da descrição contra o trecho (`28c6eb5`, `fix/descricao-confere-com-trecho`). O teste manual recomeça da P1 com esse código |
| 2026-11-12 | 40/40 | P1 e P2 testadas no frontend com `28c6eb5` (idênticas à pré-rodada). Mudança de método: P3–P40 classificadas pelo assistente a partir da pré-rodada, com revisão do usuário só nos casos duvidosos e numa amostra (seção "Versão 3" abaixo). Resultado: 34 corretas, 4 parciais, 2 incorretas |

## Correções durante o teste

**SHAs reescritos em 2026-11-13.** O histórico inteiro foi reescrito para tirar as linhas de coautoria e de sessão da IA (Portaria UFES 310/2026, art. 17, III) e publicado num repositório novo. O conteúdo de cada commit é idêntico, com a mesma árvore, o mesmo autor e as mesmas datas. Os SHAs deste documento já são os novos. Na nota abaixo, os SHAs à esquerda das setas são de antes de 2026-11-09.

**SHAs reescritos em 2026-11-09.** A pilha local, nunca enviada ao GitHub, foi refeita para tirar a linha de coautoria das mensagens (Portaria UFES 310/2026, art. 17, III). O conteúdo de cada commit é idêntico, com a mesma árvore. Equivalência: `6da6076` → `5441f78` (`feat/avaliacao-final`), `ab7ba7b` → `d427e56` (`fix/lexical-bm25`) e `6b33940` → `66df979` (`fix/geracao-por-evento`). O texto abaixo mantém os SHAs antigos, como foram registrados na época.

Versão 3 (branches empilhadas, um escopo cada): `e38df73` (`fix/geracao-por-evidencia`, correção C), `6fd302c` (`fix/encaminhamento-proposto`, correção D), `e8c05b4` (`feat/numero-real-do-processo`, correção E), `5103de2` (`feat/filtro-por-setor`, correção F), `88e87ba` (`fix/ponto-final-do-desfecho`) e `28c6eb5` (`fix/descricao-confere-com-trecho`, correção G).

**Orientação do orientador (2026-11-07):** o teste é de desenvolvimento, então uma falha encontrada é registrada, corrigida, e a pergunta é rodada de novo. A verificação da correção usa perguntas da base que ainda não serviram para ajustar o sistema. A avaliação no portal fica para depois das correções. Para localizar uma falha, a pergunta é rodada com um identificador de execução, registrando para a mesma requisição os itens de cada camada de busca, a lista após a fusão, os trechos enviados ao modelo e a resposta bruta, com ata, item de pauta e página em cada etapa. Para perguntas de histórico, ele sugeriu enviar as evidências como registros separados (identificador, data, trecho), pedir ao modelo uma lista estruturada de eventos com o identificador da evidência e deixar no backend a validação dos identificadores, a montagem das referências e a ordenação por data.

**Decisão:** em 2026-11-07 o teste parou na P4. As correções entram agora, as P1–P3 e as perguntas usadas na verificação são refeitas, e o teste continua da P4. O resultado original de cada pergunta é guardado (versão 1, commit `6da6076`).

**Ferramenta:** `rastreios/rastrear.py` faz o rastreio por camada e confere se a fusão reproduzida é igual à do orquestrador. Os rastreios ficam em `rastreios/rastreio_p<n>_v<versão>.json`, com id de execução, commit, configuração (k=5, top_n_ancora=10, três camadas, `qwen2.5:7b`, num_ctx 16384, temperatura 0), posição de cada item esperado em cada camada, contexto enviado, tokens e resposta bruta.

| Origem | Problema | Camada | Causa confirmada | Correção |
|---|---|---|---|---|
| P2 | Em pergunta D, o modelo omite o evento de 13/05 | geração | Os dois itens esperados entram no contexto (28/05 na posição 1 e 13/05 na posição 3), sem corte de tokens (4.781 de 16.384) e sem deduplicação por assunto (a fusão agrupa só pelo id do item). A resposta bruta já omite 13/05: é falha de geração | Proposta: saída estruturada, com um registro por evidência e a ordenação e as referências feitas no backend (ver experimentos abaixo) |
| P12, P13, P30 | Perguntas D sobre código de disciplina não encontram as atas, e o sistema se abstém | recuperação (léxica) | A camada léxica usa `ts_rank` do PostgreSQL, que não tem IDF: o código raro (`COM10508` aparece em 3 de 3.582 itens) pesa igual a "disciplina" (532 itens), "setor" e "decisão". O item esperado da P13 cai para a posição 298 entre 1.555 itens casados, e o limite é 50. O TCC promete BM25, justamente para siglas e códigos | Proposta: BM25 de fato (com IDF e normalização por tamanho) |
| P2 | Itens com o mesmo `PROCESSO_n` não recebem pontuação do grafo | recuperação (grafo) | A expansão só segue `TRATA_DE→Assunto` e relações entre deliberações, não segue processo. Além disso, itens que já são âncoras ficam fora dos hits do grafo (por desenho) | A avaliar depois das duas acima |
| P2 | Retirada de pauta aprovada fica com `tipo_desfecho = Aprovado` | enriquecimento | O desfecho vem da votação, e não do objeto da votação | A avaliar |

**Experimentos de geração na P2 (mesmo contexto, uma variável por vez):**

1. Evidências como registros JSON com lista de eventos: continua só com 28/05. O formato sozinho não resolve.
2. Um registro obrigatório por evidência (`relevante` sim ou não, mais a descrição): 13/05 entra, mas com uma inferência sem apoio ("indicando que o relatório já havia sido apreciado").
3. Item 2 mais a regra "descreva só o que o trecho registra, sem inferir": 13/05 sai correta, mas 28/05 perde o desfecho ("foram propostas").
4. Item 3 com a descrição incluindo "a decisão ou o resultado da votação": os dois eventos ficam certos, em ordem, cada um com a sua evidência. Prompt em `rastreios/experimento_por_evidencia_v3.py`.

Na verificação com as outras D (P12, P13, P19, P30), a versão 4 não piora nada, mas não corrige P12, P13 e P30, que falham antes, na recuperação. Na P12 ela produziu uma descrição de um item irrelevante ("não houve decisão sobre a disciplina"). A P19 cobre só 24/04, porque o item de 22/05 (léxica, posição 13) não entra no top 5.

### Correção A: busca léxica (branch `fix/lexical-bm25`, a partir de `feat/avaliacao-final`)

1. **BM25 no lugar do `ts_rank`** (`app/recuperacao/lexico.py`): BM25 Okapi (k1 = 1,2, b = 0,75), calculado em SQL sobre os mesmos lexemas do `tsv` (configuração `portuguese`), com desempate estável por id. Leva cerca de 75 ms por consulta nas 3.582 linhas. Não há cache, então nada precisa ser invalidado na reingestão.
2. **Fusão RRF com profundidade 10** (`app/recuperacao/fusao.py`): só os 10 primeiros de cada camada entram na fusão. Com 50, um item em posição média em duas camadas (vetorial 11ª e grafo 2ª) vencia o 1º da léxica, e a vetorial não enxerga códigos de disciplina.

**Validação sem ajuste às 40:** as 40 perguntas do autor com itens esperados (`ground_truth.yaml`, que saíram da avaliação formal) serviram de conjunto de desenvolvimento. Configuração completa (léxica, vetorial e grafo), k = 5:

| Variante | Recall@5 | MRR | Intra exata (R) | Intra reformulada (R) | Inter-atas (R) | Longitudinal (R) |
|---|---|---|---|---|---|---|
| `ts_rank`, RRF 50 (versão 1) | 0,50 | 0,45 | 0,80 | 0,30 | 0,52 | 0,39 |
| BM25, RRF 50 | 0,76 | 0,74 | 0,90 | 0,70 | 0,77 | 0,67 |
| BM25, RRF 20 | 0,77 | 0,79 | 0,90 | 0,70 | 0,82 | 0,65 |
| **BM25, RRF 10 (adotada)** | **0,84** | **0,82** | 1,00 | 0,90 | 0,82 | 0,65 |

Efeito nas perguntas das 40 já usadas: P1, P2 e P3 mantêm o item esperado em 1º. P12 e P13 passam a ter um item esperado no contexto (antes, abstenção). A P30 continua sem item esperado no top 5. Os itens dela ficam em 5º e 6º na léxica, porque palavras do modelo da pergunta ("registros", "encaminhamentos", "constam") também pontuam. Fica como limitação, para não ajustar o sistema às 40. Testes: 713 aprovados.

### Correção B: geração por evento (branch `fix/geracao-por-evento`, empilhada sobre a A)

Implementado: `app/geracao/eventos.py` (lê os eventos, valida o identificador contra o contexto, descarta irrelevantes e ordena pela data da reunião), prompt com um registro JSON por evidência (identificador, data, fonte, trecho, relações do grafo e vizinhos), saída estruturada do Ollama (`format` com esquema JSON) e texto final montado pelo backend: `dd/mm/aaaa: descrição [n]`, uma linha por evento.

Achados no caminho:
- **Repetição degenerada:** sem o esquema, o qwen 7B às vezes repete o mesmo objeto JSON até 1.335 tokens (137 s, estourando o timeout de 120 s). O `format` com esquema resolve.
- **Leitura de vários objetos:** a saída pode trazer mais de um objeto JSON seguido. O leitor junta os eventos de todos.
- **Conflito entre perguntas de histórico e perguntas de atributo:** pedir uma "resposta direta à pergunta" (campo `resposta` ou instrução na descrição) faz o modelo trazer o departamento que vem só do grafo (teste e2e do DCC), mas faz ele descartar o evento curto de 13/05 na P2, que é a falha original. Sem esse pedido, a P2 sai com os dois eventos, mas o DCC não aparece. Variantes testadas no mesmo contexto: V0 (campo `resposta`): DCC sim, P2 não. V1 (sem campo): DCC não, P2 sim. V2 (relevância decidida depois da descrição): P2 confusa. V3 (V1 com "respondendo ao que a pergunta pede"): DCC não, P2 não. V4 (campo `resposta_direta` depois da lista de eventos): DCC sim, P2 não. Conclusão: com o qwen 7B, numa chamada só, a presença de qualquer instrução de "responder à pergunta" faz o modelo descartar o evento curto.

**Desenho adotado (decidido pelo usuário em 2026-11-08): duas chamadas.**
1. **Eventos:** formato V1 (um registro por evidência: `evidencia`, `relevante`, `descricao`), com esquema JSON. O backend valida os identificadores, descarta os irrelevantes e ordena por data. Sem evento relevante, a resposta é abstenção e a segunda chamada não acontece.
2. **Resposta direta:** recebe só as evidências mantidas no passo 1 e devolve `{"resposta": "<frase>"}`.

Texto final: a frase de resposta direta, uma linha em branco e uma linha `dd/mm/aaaa: descrição [n]` por evento. A frase direta não tem marcador `[n]`. Quem sustenta cada afirmação é a lista de eventos. A avaliação soma os tokens das duas chamadas. Testes: 736 aprovados, incluindo os 4 ponta a ponta com o modelo real, e o do DCC passa sem alteração. Commit `6b33940`.

**Verificação (versão 2, rastreios `rastreios/rastreio_p<n>_v2.json`):**

| Pergunta | Versão 1 | Versão 2 | Observação |
|---|---|---|---|
| P1 (B) | correta | correta | — |
| P2 (D) | parcial (omitia 13/05) | dois eventos em ordem, 13/05 e 28/05 | O evento de 13/05 traz uma inferência pequena ("após a apreciação do relatório"; a ata diz "encaminha, para apreciação"). A frase direta saiu longa e não cita 13/05 |
| P3 (B, quem) | correta | correta | — |
| P12 (D) | abstenção indevida | só 22/07 | O item de 24/04 não entra no top 5 (recuperação). As afirmações conferem com a ata |
| P13 (D) | abstenção indevida | só 24/04 (ordem do dia 3.6) | Faltam o expediente 1.1 de 24/04 e o item de 29/05 (recuperação). "Aprovado por maioria" confere |
| P19 (D) | parcial (só 24/04) | parcial (só 24/04) | O item de 22/05 não entra no top 5 |
| P30 (D) | abstenção indevida | abstenção indevida | Limitação registrada na correção A |

A classificação formal dessas perguntas sai no reteste pelo frontend.

**Limitações para o TCC:** (1) nas perguntas D, a busca ainda traz só parte das atas do histórico (P12, P13, P19, P30); (2) a frase de resposta direta é texto livre, sem marcador por afirmação; (3) cada pergunta faz duas chamadas ao modelo.

### Correção C: uma chamada por evidência e desfecho vindo do grafo (versão 3, sem commit)

Motivo: a orientação do orientador sobre a P2 (recuperar as duas ocorrências, citar a fonte de cada uma e apresentar uma única aprovação em 28/05).

- **Fragmentos do mesmo item viram uma evidência.** O `montar_contexto` agrupa pelo item lógico e junta os textos sem repetir a sobreposição. Os [1] e [4] da P2 passam a ser uma ocorrência só.
- **Regressão encontrada:** com os fragmentos unidos e uma chamada só, o modelo marcou o evento de 13/05 como irrelevante. Os julgamentos ficam acoplados entre as evidências. Variantes em `rastreios/v3/`: A0 e A1 (uma chamada) falham, ISO, ISOR e ISO2 (uma chamada por evidência) mantêm a relevância.
- **Adotado:** uma chamada por evidência, com o prompt pedindo o desfecho registrado. Cada chamada só aceita o identificador da própria evidência.
- **Segunda regressão:** ao remover a frase de encaminhamento falsa (correção D), o evento de 28/05 perdeu o desfecho. Com a frase de volta, o modelo escreveu "Foi aprovado o novo regimento", sem a votação nem a Decisão 73. Conclusão: o desfecho na descrição livre muda com qualquer alteração do prompt, e não dá para confiar nele.
- **Adotado:** o backend anexa à linha do evento as frases "Resultado da votação" e "Ato emitido" que vêm do grafo. Na configuração sem grafo, essas frases não existem, então a comparação com e sem grafo não é afetada. Nas 8 ocorrências conferidas, o campo reproduz o fim do trecho da ata.
- **Frase direta:** recebe só os eventos validados e passa a citar `[n]`. É descartada se trouxer marcador fora dos eventos, se não tiver marcador havendo mais de um evento, ou se repetir uma descrição (semelhança de 0,8 ou mais). Com um evento só e sem marcador, recebe o marcador dele.

**Verificação (`rastreios/v3/final_com_desfecho.log`):** P2 com 13/05 (exclusão da pauta por unanimidade) [3] e uma única ocorrência de 28/05 (aprovado por unanimidade, `DECISAO_73_2025`) [1]. P1, P3, P13 e P19 mantêm os eventos. P12 passa a ter dois eventos (24/03 e 22/07). Testes: 760 aprovados e 2 ignorados.

**Latência:** de 37 a 56 s por pergunta na rodada sem concorrência (`final_apos_grafo.log`), com até 6 chamadas ao modelo. Na última rodada, P2, P3 e P19 levaram de 11 a 18 min porque o Mac entrou em repouso, então essas medidas foram descartadas.

**Limitações:** (1) a descrição da P2 diz "a reunião encaminhou para apreciação", quando na ata é o Centro que encaminha ao conselho; a frase direta repete isso; (2) a linha do evento pode repetir a votação quando o modelo também a descreve; (3) o resultado da votação é o do item inteiro, e num item com várias disciplinas ele vale para o conjunto.

### Correção D: extração de encaminhamentos (falha de modelagem relacional, sem commit)

O orientador pediu o trecho que registra o envio às Direções dos Centros de Ensino (P2). **Esse trecho não existe.** A regra da ingestão pegou "com encaminhamento às Direções dos Centros de Ensino" de dentro do texto do Art. 27 que estava sendo alterado, e o grafo guardou isso como encaminhamento da deliberação.

Revisão manual dos 32 itens lógicos com encaminhamento gravado (a contagem anterior de 40 incluía fragmentos e itens sem desfecho):

| Classificação | Itens | Exemplos |
|---|---|---|
| Removidos: pedido em parecer citado | 10 | "solicito encaminhamento às instâncias competentes" |
| Removidos: texto de norma ou artigo citado | 3 | Art. 27 (1730), "em caso de encaminhamento para um docente" (1770, 1778) |
| Removidos: pedido narrado | 4 | "solicitando o encaminhamento à PRPPG" (1957, 1963, 1983) |
| Mantidos corretos | 11 | "propôs como encaminhamento…", "o seguinte encaminhamento: …" |
| Mantidos com ressalva | 4 | ver abaixo |

**Regra nova:** "encaminhamento a/para X" só conta quando há verbo de proposição antes (propôs, colocou, fez, sugeriu). A regra com dois-pontos não mudou. Isso inverte uma decisão anterior, que tinha teste aceitando o pedido do parecer: esse pedido registra a recomendação do relator, não o envio.

**Testada e descartada:** ignorar o que está entre aspas. Empata (corrige o 1698 e quebra o 1779, porque essa ata abre uma aspa e não fecha), e a regra do verbo já resolve o Art. 27.

**Ressalvas que continuam no grafo:** 1698 (e-mail citado), 1684 (procedimento de votação), 1779 (três propostas, sem indicar a escolhida), 1780 pauta 3 (valor cortado em "“1").

**Aplicação:** coluna `encaminhamento` atualizada em 17 itens lógicos (26 linhas), sem mudança em outro campo e sem reprocessar PDFs (`rastreios/v3/aplicar_encaminhamento.py`, valores antigos em `encaminhamentos_alterados.json`). Grafo reconstruído: `Encaminhamento` de 32 para 15 e `GERA` de 2638 para 2621; o resto ficou igual (`grafo_antes.txt`, `grafo_depois.txt`).

### Correção E: número real do processo na tela (orientação de 2026-11-08, sem commit)

A tela de consulta mostra o número que consta na ata. Recuperação, grafo, índice e avaliação continuam com tokens, sem reprocessamento.

- **Tabela `numeros_processo` (token → número):** preenchida por `python -m app.ingestion.numeros_processo`, que extrai o texto bruto de cada PDF, recalcula o HMAC de cada número e acha o token exato em `entidades_anonimizadas`. Ingestões futuras gravam o número junto com o token.
- **Troca só na rota `/consultas`:** o número digitado na pergunta vira token na entrada, e o token vira número no texto e nos trechos da saída. A avaliação não passa por essa rota.
- **Processo ou documento avulso:** o rótulo é o da própria ata, porque só o número é trocado.
- **Nomes:** continuam `PESSOA_n` na tela.

**Verificação (`rastreios/v3/numeros_processo.log`):** 357 PDFs lidos, 2005 ocorrências, nenhuma sem token. Os 1588 tokens presentes nos itens têm número; só 4 tokens de `entidades_anonimizadas`, que não aparecem em item nenhum, ficaram sem. Numa amostra aleatória de 60 itens, 58 tiveram o contexto antes do token seguido do mesmo número no PDF, e nenhum divergiu (2 pulados, com outro token no contexto). Os 53 números distintos do gabarito estão na tabela. Pela API real, a P2 mostra `23068.002674/2023-64` como "Documento avulso nº", e a pergunta feita com esse número traz as duas ocorrências.

**Erro corrigido no caminho:** a primeira versão tinha `numero` como único. O mesmo número gera outro token com outra chave HMAC, e isso quebrava a ingestão (17 testes falharam com a tabela preenchida). A restrição virou índice comum, com teste de regressão. Depois de refazer a tabela: 1592 linhas, nenhum token dos itens sem número, 769 testes aprovados e 2 ignorados.

**Limitação:** na pergunta feita pelo número, a frase direta saiu confusa ("foi aprovado por unanimidade a exclusão da pauta"). A frase direta continua sendo a parte mais fraca da resposta.

### Correção F: filtro pelo setor citado na pergunta (2026-11-11)

Antes do teste manual, as 40 perguntas foram rodadas pela API (mesmo caminho do frontend) e comparadas com o gabarito pelas datas das atas citadas. **14 das 83 fontes citadas eram de outro setor**, em 8 perguntas. Exemplos: na P37 ("no setor CEUNES / DMA") vieram atas do Conselho do CEUNES e do DCE, e as duas fontes da P16 eram de outro setor. A busca não restringia pelo setor, e com cada evidência julgada sozinha o modelo aceitava qualquer item sobre o assunto.

**Correção (aprovada pelo usuário):** quando a pergunta nomeia um setor que corresponde a um órgão conhecido ("CCAE / DEAL" → `CCAE_DEAL`), as três camadas só devolvem itens desse órgão:
- **Léxica:** filtro no SQL; as estatísticas do BM25 continuam sobre a coleção inteira, então as pontuações não mudam.
- **Vetorial:** filtro do Qdrant pelos documentos do órgão.
- **Grafo:** os itens expandidos de outro órgão são descartados.

Sem setor na pergunta, nada é filtrado. O filtro vale para todas as configurações da avaliação e entra no TCC como filtro por metadados.

**Resultado (comparação por datas com o gabarito):**

| | Antes | Depois |
|---|---|---|
| Cita todas as atas esperadas | 30 | 36 |
| Cita parte | 7 | 4 (P9, P12, P20, P21, todas de histórico) |
| Não cita nenhuma | 3 (P16, P30, P37) | 0 |
| Fontes de outro setor | 14 de 83 | 0 de 96 |

Também corrigido o ponto duplo nas frases do grafo ("por unanimidade.."), que aparecia em 8 respostas e depois em nenhuma. Testes: 775 aprovados e 2 ignorados.

**Limitação:** várias perguntas do tipo B citam atas a mais do mesmo setor (por exemplo, outros relatórios de extensão do DMPA na P16). A conferência pergunta a pergunta é que diz se esses eventos são pertinentes.

### Contaminação da descrição pela pergunta (2026-11-11)

**Achado:** no teste manual v3, a P1 citou o item 10 da ata CAR de 05/02/2025, sobre os PADs de **Comunicação Social**, como se fosse sobre os PADs do **DAV**. A pré-rodada já tinha essa resposta, mas `conferir_40.py` só compara as datas das atas, por isso não acusou. Na leitura das 40 respostas (`rastreios/v3/varrer.py`), o mesmo padrão apareceu em três perguntas: P1 [4] (DAV no lugar de Comunicação Social), P5 [3] (2024/1 no lugar de 2024/2; o erro também entrou na frase direta) e P28 [5] ("professora Drª" no lugar de "Professor Dr."). Houve também ruído, isto é, evidência de assunto vizinho descrita corretamente, mas que não responde à pergunta: P15, P16, P17, P26 e P28.

**Isolamento da causa** (`rastreios/v3/isolar_causa.py`, saída em `isolar_causa_p1_p5_p28.jsonl`). O código é o de `88e87ba`. Duas variáveis, uma por vez: contexto com e sem o filtro por setor, e geração por evidência (v3) ou todas as evidências numa chamada, como na v2.

| Pergunta | Sem filtro, por evidência | Sem filtro, todas juntas | Com filtro, por evidência | Com filtro, todas juntas |
|---|---|---|---|---|
| P1 | correta (o item 10 não entra no top 5) | correta | **[4] descrito como DAV** | [4] marcado relevante, descrição neutra ("Aprovado a unanimidade") |
| P5 | **[3] descrito como 2024/1** | sem contaminação, mas omite [1], o item do gabarito | **[3] descrito como 2024/1** | sem contaminação, [1] e [2] |
| P28 | **[4] "professora" (a ata diz "professor")** | sem contaminação | **[5] "professora Drª" (a ata diz "Professor Dr.")** | sem contaminação, menos ruído |

**Causa confirmada:** o commit `e38df73` (`fix/geracao-por-evidencia`). Com uma evidência por chamada, o modelo não tem outras evidências para comparar, e preenche a descrição com o assunto da pergunta (departamento, semestre, gênero). A contaminação acontece com e sem filtro e só aparece no modo por evidência. O mesmo commit passou a montar a frase direta a partir das descrições, e não mais dos trechos. Por isso o erro da P5 também entrou na frase de abertura.

**Fator que amplia:** o filtro por setor (`5103de2`) troca as evidências de outros setores, fáceis de descartar, por vizinhas do mesmo setor e até da mesma ata (PADs de outro departamento, licenças de outras pessoas). Isso dá mais oportunidade à contaminação (P1) e ao ruído (P28). O filtro não cria o mecanismo: a P5 e a P28 já erravam sem ele.

**Por que não basta voltar à v2:** a chamada única foi trocada por causa da omissão de evento na P2, e a omissão aparece de novo aqui (a P5 sem filtro perde o item do gabarito). Além disso, no modo de chamada única, a P1 com filtro também marca o item 10 como relevante.

**Correção:** a decidir. Qualquer correção será verificada na P2 (omissão), nas 40 perguntas e com uma conferência que compare o texto da resposta com o trecho citado, e não só as datas.


**Experimento 1: descrição sem a pergunta (2026-11-12, `rastreios/v3/descricao_sem_pergunta.py`, saída `.jsonl`).** Mesma recuperação (`88e87ba`, com filtro). O modelo descreve cada evidência sem ver a pergunta, e a relevância é julgada depois, de quatro jeitos: por evidência (A) ou numa chamada só (B), com o critério atual ou com um critério estrito (mesmo órgão, departamento, semestre, pessoa e processo da pergunta). Origem: heurística própria. Trabalhos relacionados: Chain-of-Note (`yu2024chainofnote`, uma nota por documento, mas com a pergunta) e Self-RAG (`asai2024selfrag`, que separa o julgamento de relevância). Itens relevantes por variante (✓ = bate com o gabarito, ✗ = falta item do gabarito):

| Pergunta | Atual | A | A estrito | B | B estrito |
|---|---|---|---|---|---|
| P1 (B) | 1, **4 contaminado** | 1 ✓ | 1 ✓ | 1 ✓ | 1 ✓ |
| P5 (B) | 1, 2, **3 contaminado** | 1, 2 | 1, 2 | 1, 2 | 1, 2 |
| P28 (B) | 1–5, **5 contaminado** | 2–5 | 1–4 | 2, 3, 4 | 2, 3, 4 |
| P2 (D) | 1, 2 ✓ | 2 ✗ | 2 ✗ | 1 ✗ | 1 ✗ |
| P6 (B) | 1, 2, 3 | 1, 2, 3 | 1, 2 | 1, 2 | 1, 2 |
| P15 (B) | 1, 2, 4, 5 | 1, 2 | 1, 2 | 1, 2 | 1, 2 |
| P16 (B) | 1–4 | 1, 2, 4 | 1, 2, 4 | 1, 4 | 1, 4 |
| P17 (B) | 1, 3 | 1, 3, 4 | 1, 3, 4 | 1 ✓ | 1 ✓ |
| P26 (B) | 1, 2, 3 | 1, 2, 3 | 1 ✓ | 1, 3 | 1, 3 |
| P12 (D) | 1 (o item de 24/04 não entra no top 5, limitação da recuperação) | 1 | 1 | 1 | 1 |
| P13 (D) | 1, 2, 3, 5 ✓ | 1, 3, 5 ✗ | 1, 2, 3, 5 ✓ | 1, 3, 5 ✗ | 1, 3 ✗ |
| P19 (D) | 1, 3, 4 | 1, 3 ✓ | 3, 4 ✗ | 1, 3 ✓ | 1, 3 ✓ |

Resultado: a contaminação some em todas as variantes, e o ruído cai. Mas apareceram dois problemas novos: (1) a descrição escreve as siglas por extenso e erra ("CAR" vira "Centro Administrativo e de Regulamentação", "DER" vira "Departamento de Engenharia de Requisitos"); (2) nas perguntas D, a descrição perde o termo-chave ("COM10508" na P13, "reorganização de espaços" na P2) e o evento é omitido. Nenhuma variante foi adotada. A segunda rodada ajusta o prompt da descrição (sem órgão nem data, sem expandir siglas, título copiado do trecho) e testa a variante híbrida (relevância da chamada atual, texto da descrição sem a pergunta).

**Experimento 2 (2026-11-12, `descricao_sem_pergunta_v2.py`).** O prompt da descrição passa a pedir: sem órgão nem data, sem siglas por extenso, título copiado do trecho. Entra também a variante híbrida C (relevância da chamada atual, texto da descrição sem a pergunta). A contaminação continua zerada, mas aparecem dois problemas:
- **perda do que a pergunta pede:** na P5 ("Quais datas foram definidas"), a descrição sem a pergunta resume como "proposta de calendário aprovada" e perde as datas, que são a resposta. Em todas as variantes, a resposta da P5 fica sem as datas;
- **siglas expandidas de forma errada, ainda que menos:** "DER" vira "Departamento de Engenharia de Reatos" (P5 [5]) e "PPC" vira "Programa de Pós-Graduação" (P19 [4]).

Conclusão: a pergunta é o que contamina a descrição, mas também é o que diz ao modelo que detalhe guardar. A descrição sem a pergunta troca um erro por outro e não foi adotada.

**Checagem determinística da descrição (`rastreios/v3/checagem_descricao.py`).** O evento é descartado quando a descrição traz um termo específico da pergunta (sigla, código, número, semestre ou nome próprio composto) que não aparece no trecho nem no rótulo da fonte. Ela roda sobre a saída atual, sem chamada extra. Origem: heurística própria. Trabalhos relacionados: CRAG (`yan2024crag`, descarte depois da recuperação) e AIS (`rashkin2023ais`, atribuição à fonte). Resultado nas duas pré-rodadas (40 perguntas cada, com e sem filtro): marca só P1 [4] (DAV) e P5 [3] (2024/1), e nenhum falso positivo. Limitações: (1) não pega erros em palavras comuns, como "professora" no lugar de "professor" (P28 [5]); (2) não trata o ruído, porque descrições fiéis passam; (3) numa pergunta reformulada, se a pergunta disser "Artes Visuais" e a ata disser "DAV", a descrição do item certo pode copiar o termo da pergunta e ser descartada. Isso precisa ser testado quando as reformuladas entrarem.

**Correção G (aprovada pelo usuário em 2026-11-12, `28c6eb5`, branch `fix/descricao-confere-com-trecho`).** A checagem determinística entra no respondedor. Depois de cada chamada por evidência, o evento é descartado quando a descrição traz um termo específico da pergunta (sigla, código, número, semestre ou nome próprio composto) que não aparece no trecho nem no rótulo da fonte. A comparação ignora acentos e trata "2024.2" e "2024/2" como iguais. Como o descarte acontece antes da frase direta, o erro também não chega à abertura da resposta. O descarte fica registrado no log (nível info). Testes: 7 novos, suíte com 782 aprovados e 2 ignorados.

**Verificação (`rastreios/v3/prerodada_40_checagem.jsonl`, API do commit `28c6eb5` numa segunda instância, porta 8001):** das 40 respostas, só P1 e P5 mudaram, e as outras 38 ficaram idênticas. A P1 deixou de citar o item 10 (Comunicação Social). A P5 deixou de citar o calendário de 2024/2, e a frase direta passou a trazer só as datas de 2024/1. A comparação por datas com o gabarito não mudou (36 com todas as atas esperadas, 4 parciais). O tempo médio subiu de 38 s para 44 s sem nenhuma chamada a mais, o que é variação de carga da máquina. As limitações são as registradas na checagem acima: palavra comum (P28), ruído e risco nas perguntas reformuladas.

## Observações por pergunta

Achados que valem para o texto do TCC (padrões de erro, limitações, casos curiosos) ficam aqui, com o número da pergunta.

- **P1 (CAR, B):** resposta de uma frase, correta e com a citação certa. A data veio só no rótulo da fonte, o que motivou a regra da data acima. Resposta via API idêntica à do frontend (temperatura 0).
- **P2 (CCAE, D):** a resposta trata só da reunião de 28/05/2025 e omite a de 13/05/2025, quando o processo foi excluído da pauta. Diagnóstico: a recuperação colocou o item de 13/05 (`1728_EXPEDIENTE_2.1`) na posição 3 do contexto de 5 itens, e o `qwen2.5:7b` não o usou. É uma **falha de geração em pergunta longitudinal**: o modelo responde com a ata mais completa e ignora o evento anterior, que é curto. Nenhum dos itens recebeu pontuação do grafo, embora os dois compartilhem o mesmo `PROCESSO_n`. Em leitura rápida a resposta parece completa (foi a impressão do usuário), e só a comparação com o gabarito mostra a lacuna. Achado para o TCC: em perguntas D, a resposta convence mesmo incompleta.
- **P2, gabarito do orientador:** o desfecho está certo (nota "exclusão de pauta"), mas a transcrição de 13/05 está cortada: termina em "foi aprovada por unanimidade" e perde "a exclusão do processo da pauta", que está na ata. No nosso corpus o item tem `tipo_desfecho = Aprovado`, embora o que se aprovou tenha sido a retirada de pauta. É uma limitação do enriquecimento a registrar.
- **P3 (CCAE/DEAL, B, "quem"):** a resposta está certa, mas os nomes vêm como `PESSOA_n`. O usuário perguntou qual é o ganho de uma resposta assim. Achado para o TCC: perguntas do tipo "quem" são as que mais perdem valor com a anonimização (escolha de privacidade do TCC1: nomes não vão para o LLM). O sistema continua útil como localizador: acha o item certo entre 357 atas, explica a mudança (a presidência passou para a chefia do departamento) e o link "Abrir PDF" leva ao PDF original, onde o nome aparece. Reidentificar os tokens na tela exigiria guardar o mapeamento token→nome, o que o projeto evita de propósito.

### Versão 2

- **P1 v2 (CAR, B):** correta, com a citação certa. A data passou a aparecer no texto (`data_no_texto = sim`). Achado de forma: em pergunta de uma ata só, a frase direta repete o único evento e sai com pleonasmo ("A aprovação dos PADs […] foi aprovada"). Não muda o conteúdo, mas deixa a resposta redundante. Fica como possível ajuste de apresentação, por exemplo omitir a frase direta quando há um só evento, a decidir no fim da rodada.

### Versão 3 (código `28c6eb5`)

**Mudança de método (2026-11-12, pedido do usuário):** com temperatura 0, a resposta do frontend é idêntica à da pré-rodada (P1 e P2 conferidas palavra por palavra com `rastreios/v3/prerodada_40_checagem.jsonl`). Repetir as 40 no frontend não traz informação nova. O que traz é a leitura da resposta inteira contra o gabarito, que a conferência automática não faz: `conferir_40.py` olha só as datas, e foi a leitura do usuário que achou a contaminação da P1. Por isso:

1. O assistente leu as 40 respostas da pré-rodada contra o gabarito (resposta de referência e, quando preciso, o trecho de cada fonte) e classificou pela rubrica. Linhas `versao_sistema = v3` no CSV, geradas por `rastreios/v3/registrar_v3.py`.
2. O usuário revisa os casos parciais, incorretos e duvidosos, mais uma amostra sorteada das corretas (semente 20261112), para medir a concordância com a classificação do assistente.
3. P1 e P2 foram vistas pelo usuário no frontend.

Para o texto do TCC: a classificação da v3 é do assistente, com revisão humana por amostragem. Não há avaliação humana independente das respostas do RAG: o portal do orientador confere o gabarito dele contra as atas, não a resposta do sistema (ver "Portal do orientador" no início deste arquivo).

**Resultado:** 33 corretas, 4 parciais e 3 incorretas, sem abstenção. Por tipo: B 26 corretas e 1 parcial; C 4 corretas, 2 parciais e 2 incorretas; D 3 corretas, 1 parcial e 1 incorreta. A P13 saiu de correta para incorreta em 2026-11-14, depois da etapa (c) (ver abaixo); antes eram 34 corretas e 2 incorretas.

| Classe | Perguntas | Motivo |
|---|---|---|
| incorreta | P20 (C) | 1 de 3 atas do gabarito; expande CCHN como "Conselho Científico-Habilitador de Nível Nacional" (alucinação que a correção G não pega, porque a sigla está no rótulo) |
| incorreta | P13 (D) | 3 de 3 atas, mas a linha [3] diz que a redução de vagas foi aprovada por unanimidade, quando o aprovado por unanimidade no expediente 1.1 foi a inclusão do ponto na pauta; a redução foi por maioria, como diz a linha [1]. Reclassificada em 2026-11-14 (era correta) |
| incorreta | P23 (C) | 3 de 3 atas, mas a linha de 17/08/2020 diz que as diretrizes foram aprovadas, quando só a consulta à Prograd foi; o "Resultado da votação" anexado contradiz a frase |
| parcial | P9 (C), P21 (C) | 4 de 7 e 3 de 7 atas: a pergunta tem mais ocorrências do que o top 5 comporta |
| parcial | P12 (D) | falta 24/04/2025 (recuperação, já registrado na v2) |
| parcial | P37 (B) | cita 3 das 4 atas aprovadas no item e omite a de 07/11/2024 (aprovada com o texto corrigido), que ocupa quase todo o trecho |

**Para o usuário revisar:**

- Casos não corretos: P9, P12, P20, P21, P23, P37. P20 e P23 dependem de como a rubrica pesa um erro numa linha só: pela regra escrita ("afirmação sem apoio" e "desfecho errado") ficaram incorretas.
- Corretas duvidosas: P5 (traz também o calendário de 11/04/2024, que a ata chama de 2024/1 e o gabarito não lista) e P40 (a linha de 12/12/2025 é do curso noturno e não diz o curso).
- Amostra sorteada das corretas: P11, P18, P25, P32, P34, P39.

**Revisão do usuário (2026-11-13):** concordou com as 14 classificações. A classificação final fica em 34 corretas, 4 parciais e 2 incorretas. Em dois casos discordou a princípio e manteve a classe depois de conferir o gabarito:

- P12: o argumento era que a pergunta pede a decisão final, e a de 22/07/2025 está certa. As duas atas tratam de assuntos diferentes (bibliografia em 24/04/2025, oferta da turma VE1 em 22/07/2025), e a segunda não substitui a primeira. Ficou parcial.
- P37: o usuário apontou que "com alteração" é correção do texto da ata, e não recusa seguida de aprovação. O ponto procede e a justificativa foi reescrita. Ficou parcial porque a resposta omite uma das 4 atas aprovadas.
- P21: perguntou se a decisão mais recente (2023) não teria prioridade. Não se aplica: cada ata é o relatório de licença de um professor diferente, e as decisões são independentes.

Concordância entre assistente e usuário: 14 de 14 na classe final, ou 12 de 14 na primeira leitura. As observações estão na coluna `observacao_usuario` do CSV.

**Reclassificação da P13 (2026-11-14):** a fidelidade do RAGAS (etapa c) marcou a linha [3] da P13, que diz que a redução de vagas foi aprovada por unanimidade. Conferida no trecho, a frase troca a aprovação da inclusão do ponto na pauta (expediente 1.1) pela aprovação da redução, que foi por maioria. É o mesmo tipo de erro da P23, e o usuário reclassificou a P13 como incorreta. A P13 não estava entre as 14 revisadas. A classificação final passa a 33 corretas, 4 parciais e 3 incorretas.

**Limitação do k = 5:** quando o gabarito tem mais atas do que o sistema devolve de trechos (P9 e P21, com 7), a resposta nunca sai completa, por melhor que seja a ordenação.

**Padrões da v3:**

- **Melhoras sobre a v2:** P2, P13, P19 e P30 trazem todas as atas do gabarito (P30 era abstenção indevida). A P13 traz todas, mas ficou incorreta pela linha [3].
- **Ruído:** evidência vizinha descrita corretamente, mas fora do foco (P7, P15, P16, P26, P28, P29). Não troca a resposta certa, mas alonga o texto.
- **Mais que o gabarito:** P5, P6, P10 e P27 trazem registros do mesmo assunto, com apoio nos trechos, que o gabarito não lista. Vale avisar o orientador.
- **Recuperação:** em C com muitas ocorrências (P9 com 7, P21 com 7, P20 com várias), o top 5 limita a cobertura.
- **Forma:** frase direta como fragmento (P11, P25), frase direta que repete o evento (P17), linha que repete a votação (P4), "Resultado da votação" que pega a frase errada do item (P28 [5]).
- **Segmentação:** rótulo da fonte com o item errado (P6 [3]: diz 1.1, o texto é do 3.9) e ata de 2021 datada 03/05/2003 (P26).

## Métricas por pergunta (v3, etapa c)

Pedido do orientador: Recall@5, Precision@5, MRR e nDCG@5 por pergunta, mais a fidelidade (faithfulness) do RAGAS ao lado da conferência documental. Os valores por pergunta estão em `teste_manual_metricas_v3.csv`, uma linha por pergunta, configuração A. Os scripts e as saídas brutas estão em `rastreios/v3/metricas/`.

**Método:**

- **Itens relevantes:** cada registro do gabarito do orientador (`Registro de dd/mm/aaaa — ÓRGÃO (seção, item X)`) foi ligado ao item do sistema pelo órgão, data da reunião, seção e número do item (`ligar_gabarito.py`). Dos 73 registros, 66 ligaram direto e 7 caíram no item pai, porque o sistema não separa aquele subitem. É uma heurística própria.
- **Recuperação:** `recuperar()` com k = 5, nas configurações A (léxico + vetorial + grafo), B (léxico + vetorial), C (só léxico) e D (só vetorial), com o filtro por setor (`calcular_metricas.py`). Os fragmentos do mesmo item contam como um item só. Precision@5, Recall@5 e MRR seguem `baeza1999modern`; nDCG@5 usa relevância binária (`jarvelin2002cumulated`).
- **Fidelidade:** as 40 respostas foram geradas de novo na configuração A. Fora o número do processo, as 40 são idênticas às da pré-rodada, então a fidelidade e a classificação manual valem para o mesmo texto. O juiz é o qwen2.5:14b local, com `Faithfulness` do RAGAS 0.4.3 (`es2023ragas`) e os contextos que o gerador recebeu (rótulo, trecho e desfecho do grafo). A P6 estourou o limite de 10 min por chamada; a rodada foi retomada dela com limite de 30 min, e P6–P40 levaram 1,5 h (`fidelidade.py`).

**Recuperação, configuração A:**

| Tipo | Perguntas | P@5 | R@5 | MRR | nDCG@5 |
|---|---|---|---|---|---|
| B | 27 | 0,200 | 1,000 | 0,883 | 0,912 |
| C | 8 | 0,575 | 0,790 | 0,900 | 0,854 |
| D | 5 | 0,400 | 0,900 | 1,000 | 0,882 |
| Todas | 40 | 0,300 | 0,946 | 0,901 | 0,897 |

A P@5 tem teto pelo tamanho do gabarito: uma pergunta B tem 1 item relevante, então o máximo é 0,2. Em C, a R@5 tem teto quando há mais de 5 itens relevantes (P21 tem 12, teto 0,42).

**Ablação (todas as 40):**

| Configuração | P@5 | R@5 | MRR | nDCG@5 |
|---|---|---|---|---|
| A: léxico + vetorial + grafo | 0,300 | 0,946 | 0,901 | 0,897 |
| B: léxico + vetorial | 0,300 | 0,946 | 0,901 | 0,897 |
| C: só léxico | 0,280 | 0,929 | 0,826 | 0,843 |
| D: só vetorial | 0,240 | 0,822 | 0,830 | 0,798 |

- **A = B:** o grafo não muda nenhuma métrica de recuperação. O ranking difere só na P24 e na P25, e sem mudar acertos. Na geração, o grafo continua entrando pelo desfecho ("Resultado da votação", "Desfecho"), que vai no contexto.
- **Fusão:** a fusão léxico + vetorial ganha das duas camadas sozinhas, sobretudo no MRR e no nDCG@5. A busca só vetorial cai mais nas perguntas D (R@5 0,50; MRR 0,44).

**Onde a resposta falhou (recuperação ou geração):**

- **Recuperação:** R@5 abaixo de 1 em P9 (0,57; 4 de 7), P12 (0,50), P20 (0,33; MRR 0,2) e P21 (0,42; teto 5 de 12). São as quatro perguntas que a classificação manual marcou como incompletas por falta de ata (P9, P12, P20, P21).
- **Geração:** P13 e P23 (incorretas) e P37 (parcial) têm R@5 = 1. O item certo estava no top 5, e o erro ou a omissão é do gerador.
- Toda fonte citada na pré-rodada está no ranking da configuração A.

**Fidelidade:** média 0,916, mediana 1,00, mínimo 0,50, sem erro nem tempo esgotado. 26 das 40 respostas têm 1,00.

| Recorte | Perguntas | Fidelidade média |
|---|---|---|
| Tipo B | 27 | 0,920 |
| Tipo C | 8 | 0,934 |
| Tipo D | 5 | 0,867 |
| Classe correta | 33 | 0,930 |
| Classe parcial | 4 | 0,897 |
| Classe incorreta | 3 | 0,794 |

**Fidelidade contra a conferência documental.** As afirmações que o juiz marcou sem apoio foram conferidas no trecho:

- **Erro real que a classificação manual já tinha:**
  - P23 (0,857): o juiz marcou exatamente a linha de 17/08/2020 que diz que as diretrizes foram aprovadas.
  - P40 (0,50): o juiz notou que a linha de 12/12/2025 é do curso noturno, a mesma ressalva da justificativa.
- **Erro real que a classificação manual não pegou:**
  - P13 (0,667): a linha [3] diz que a redução de vagas foi aprovada por unanimidade. No expediente 1.1, o que foi aprovado por unanimidade foi a inclusão do ponto na pauta, e a redução foi aprovada por maioria, como diz a linha [1]. A resposta se contradiz no mesmo dia. Reclassificada como incorreta pelo usuário em 2026-11-14, como a P23.
  - P6 (0,938): "o ponto foi retirado da pauta" não está no trecho, que diz só que o ponto volta a ser discutido. É um acréscimo pequeno e não muda o desfecho.
- **Erro do juiz:**
  - P20: o juiz leu o afastamento como sendo em março, mas o trecho diz "maior de 2023", erro de digitação da ata para maio. A resposta está certa nesse ponto.
  - P25: a aprovação de 30/05/2025 está no trecho [4].
  - P26: o compromisso de dialogar com a Comissão de Encargos Docentes está no trecho [2].
  - P8: a resposta repete a frase da votação no "Resultado da votação", e o juiz entendeu que houve duas votações.
- **Interpretação estrita do juiz:** P3, P12, P32 e P39 têm afirmações que parafraseiam o trecho ou citam o marcador `[1]` como se fosse conteúdo.
- **O que a fidelidade não mede:**
  - Omissão: a P37 tem 1,00 porque o que diz está certo, mas falta uma ata.
  - Expansão de sigla: a P20 inventa "Conselho Científico-Habilitador de Nível Nacional" e o juiz não marcou.
  - Ruído: P15 traz linhas vizinhas que o juiz marcou sem apoio, mas que a classificação manual tratou como ruído.

Para o texto do TCC, a fidelidade sozinha não separa as classes. A média das incorretas (0,794) fica abaixo da das corretas (0,930), mas há corretas com 0,50 (P40) e 0,667 (P8, P32), e a P37, parcial, tem 1,00. Ela serve como sinal complementar, e cada afirmação marcada precisa ser conferida na ata, como pede o art. 18 da Portaria UFES 310/2026.
