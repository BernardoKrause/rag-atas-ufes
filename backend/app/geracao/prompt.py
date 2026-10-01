from __future__ import annotations

from app.geracao.tipos import EvidenciaNumerada

FRASE_ABSTENCAO = (
    "Não encontrei nas atas disponíveis informação suficiente para responder a essa "
    "pergunta."
)

SISTEMA = f"""Você responde perguntas sobre atas de reuniões de órgãos colegiados da UFES \
usando exclusivamente as evidências fornecidas.

Regras:
- Use apenas as evidências numeradas. Não use conhecimento externo.
- Cite a evidência que sustenta cada afirmação com o marcador [n], onde n é o número \
da evidência. Exemplo: "O conselho aprovou a proposta [2]."
- Os assuntos de itens vizinhos servem apenas de contexto e não podem ser citados.
- Se as evidências não permitirem responder, responda exatamente: "{FRASE_ABSTENCAO}"
- Responda em português, de forma direta."""


def _formatar_evidencia(evidencia: EvidenciaNumerada) -> str:
    linhas = [f"[{evidencia.numero}] {evidencia.fonte.rotulo}", evidencia.texto]
    linhas.extend(evidencia.frases_grafo)
    if evidencia.assunto_anterior:
        linhas.append(
            f"(Item anterior na mesma ata, não citável: {evidencia.assunto_anterior})"
        )
    if evidencia.assunto_posterior:
        linhas.append(
            f"(Item posterior na mesma ata, não citável: {evidencia.assunto_posterior})"
        )
    return "\n".join(linhas)


def montar_prompt(
    pergunta: str, evidencias: list[EvidenciaNumerada]
) -> tuple[str, str]:
    blocos = "\n\n".join(
        _formatar_evidencia(evidencia) for evidencia in evidencias
    )
    return SISTEMA, f"Evidências:\n\n{blocos}\n\nPergunta: {pergunta}"
