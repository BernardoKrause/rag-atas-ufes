# RAG Atas UFES

Sistema Graph-RAG para consulta em linguagem natural a atas de reuniões colegiadas da UFES (câmaras departamentais, conselhos de centro, câmaras locais e colegiados de curso).

Desenvolvido como Trabalho de Conclusão de Curso (TCC) em Ciência da Computação — UFES.

## Arquitetura

- **Segmentação estrutural** das atas por item de pauta (não por tamanho fixo de texto)
- **Extração de entidades e relações** (órgãos, datas, processos, assuntos, deliberações, encaminhamentos)
- **Recuperação híbrida em 3 camadas**: busca léxica (BM25), busca vetorial (embeddings) e travessia em grafo
- **Geração de resposta com citação de fontes** (atas, itens de pauta e processos utilizados)

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python / FastAPI |
| Frontend | React.js / TypeScript |
| Metadados | PostgreSQL |
| Busca vetorial | Qdrant |
| Grafo | Neo4j |
| LLM (geração e avaliação) | Qwen2.5 7B e 14B via Ollama (local) |

A extração usa OCR (Tesseract, português) só nas páginas sem camada de texto, como atas escaneadas ou PDFs com o texto convertido em desenho.
Instale com `brew install tesseract tesseract-lang` (macOS) ou `apt install tesseract-ocr tesseract-ocr-por` (Linux).
A ingestão completa exige o Tesseract: sem ele, a extração para na primeira página sem camada de texto (atas escaneadas).

Todos os serviços de dados rodam via Docker Compose (self-hosted).
Os testes usam um Neo4j separado (`neo4j-teste`, porta 7688), então rodar a suíte não apaga o grafo de desenvolvimento.
O Postgres é o mesmo do desenvolvimento: cada teste roda numa transação desfeita no fim, sem deixar resíduo. Por isso não rode a suíte em paralelo nem durante a ingestão completa, porque as transações podem travar umas às outras.

## Ingestão do corpus

Para processar o corpus inteiro de ponta a ponta (extração e pseudonimização, segmentação, enriquecimento, indexação no Qdrant e grafo no Neo4j):

```bash
cd backend
python -m app.ingestion.completa
```

Todas as etapas são idempotentes, então a reexecução atualiza o que mudou sem duplicar nada. Ao final, o comando lista os documentos com OCR e os documentos sem item de pauta.

## Frontend

Interface web em React + TypeScript (Vite + Tailwind CSS) para consultas em linguagem natural, com a resposta e as fontes citadas.

```bash
cd frontend
cp .env.example .env   # opcional; por padrão a API é http://localhost:8000
npm install
npm run dev            # http://localhost:5173
npm test
```

Para apontar para outra API, defina `VITE_API_URL` em `frontend/.env` (padrão `http://localhost:8000`).

A API precisa estar rodando (`cd backend && uvicorn app.main:app`).
A origem do frontend precisa estar em `CORS_ORIGENS` no `.env` da API (padrão `["http://localhost:5173"]`); abrindo por `127.0.0.1` ou pelo `npm run preview` (porta 4173), adicione essa origem, senão a tela acusa API fora do ar.

## Status

Projeto em desenvolvimento incremental, dividido em partes (um PR por parte).

| Parte | Etapa | Status |
|---|---|---|
| 1 | Infraestrutura | Concluída |
| 2 | Ingestão (coleta, extração e anonimização) | Concluída |
| 3 | Segmentação estrutural por item de pauta | Concluída |
| 4 | Extração de entidades/relações e grafo | Concluída |
| 5 | Indexação vetorial e léxica | Concluída |
| 6 | Recuperação híbrida | Concluída |
| 7 | Geração com citação de fontes | Concluída |
| 8 | API de consulta | Concluída |
| 9 | Frontend | Concluída |
| 10 | Ingestão completa do corpus e validação manual | Concluída |
| 11 | Avaliação final (rodada registrada e experimentos) | Concluída |

## Reprodução da avaliação

A avaliação do TCC foi a rodada registrada de 19/11/2026 (`python -m app.avaliacao.rodada`) e os experimentos complementares (`python -m app.avaliacao.experimentos`). A tag `tcc2-avaliacao` marca o código dessa versão.

**O que não está no repositório:** as atas (PDFs) e o inventário, a referência validada (perguntas, respostas esperadas e evidências), os bancos de dados, os registros da rodada, a chave da pseudonimização e o arquivo `.env`. As atas são públicas e precisam ser obtidas nos sítios dos órgãos; a reprodução integral depende de reconstruir o corpus e de usar os mesmos arquivos de modelo.

**Ambiente da rodada:** Apple M5 (10 núcleos), 16 GB de memória unificada, macOS 26.5, Python 3.13. Serviços: PostgreSQL 16.14, Qdrant 1.19.0, Neo4j 5.26.29 Community (fixados no `docker-compose.yml`) e Ollama 0.34.4, rodando direto no macOS para usar a GPU.

**Modelos:**

| Uso | Modelo | Identificação |
|---|---|---|
| Geração | `qwen2.5:7b` | digest `845dbda0ea48`, Q4_K_M |
| Juiz (RAGAS 0.4.3) | `qwen2.5:14b` | digest `7cdf5a0187d5`, Q4_K_M |
| Embeddings | `PORTULAN/serafim-100m-portuguese-pt-sentence-encoder-ir` | revisão `f27c45d` |
| Nomes (pseudonimização) | `Gpaiva/NERDE-base` | revisão `02a72c8` |

**Passos:**

1. Copie `.env.example` para `.env` e preencha, incluindo `ANONYMIZATION_SECRET_KEY` e o caminho do corpus. A mesma chave precisa ser usada em toda a reconstrução, porque os pseudônimos dependem dela.
2. Suba os serviços com `docker compose up -d postgres qdrant neo4j neo4j-teste` e crie as tabelas com `cd backend && alembic upgrade head`.
3. Instale as dependências: `pip install -r requirements.txt -r requirements-avaliacao.txt`, e baixe os modelos no Ollama (`ollama pull qwen2.5:7b` e `ollama pull qwen2.5:14b`), conferindo os digests com `ollama list`.
4. Coloque os PDFs e o `inventario_atas.csv` no caminho configurado e rode `python -m app.ingestion.completa`.
5. Rode as etapas da avaliação contra a referência validada, nesta ordem: `recuperacao`, `geracao --repeticao 1`, `k_ampliado`, `geracao --repeticao 2`, `geracao --repeticao 3`, `ragas` e `metricas`, sempre com `--referencia <arquivo> --saida <pasta>`. Cada etapa pode ser retomada e grava no `manifesto.json` da pasta o commit, as versões dos dados e dos modelos e os parâmetros.
6. Os experimentos complementares usam `python -m app.avaliacao.experimentos setor` e `abstencao --perguntas <arquivo>`, com a mesma referência.

Esses passos não foram repetidos a partir de uma cópia limpa do repositório.

## Licença

MIT — ver [LICENSE](LICENSE).
