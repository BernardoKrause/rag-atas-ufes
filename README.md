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
| LLM (dev) | Ollama (local) |
| LLM (avaliação final) | Claude 3 Sonnet (API Anthropic) |

Todos os serviços de dados rodam via Docker Compose (self-hosted).

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
| 9 | Frontend | Próxima |
| 10 | Ingestão completa do corpus e validação manual | Pendente |
| 11 | Avaliação final | Pendente |

## Licença

MIT — ver [LICENSE](LICENSE).
