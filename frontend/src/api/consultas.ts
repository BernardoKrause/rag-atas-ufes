export interface FonteSaida {
  numero: number
  item_id_canonico: string
  rotulo: string
  trecho: string
  pagina: number | null
  url_pdf: string
}

export interface RespostaConsulta {
  texto: string
  abstencao: boolean
  fontes: FonteSaida[]
}

export type TipoErroConsulta = 'indisponivel' | 'interno' | 'rede'

export class ErroConsulta extends Error {
  readonly tipo: TipoErroConsulta

  constructor(tipo: TipoErroConsulta) {
    super(tipo)
    this.name = 'ErroConsulta'
    this.tipo = tipo
  }
}

export const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export function ehCancelamento(erro: unknown): boolean {
  return typeof erro === 'object' && erro !== null && (erro as { name?: unknown }).name === 'AbortError'
}

export async function consultar(pergunta: string, signal?: AbortSignal): Promise<RespostaConsulta> {
  let resposta: Response
  try {
    resposta = await fetch(`${API_URL}/consultas`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pergunta }),
      signal,
    })
  } catch (erro) {
    if (ehCancelamento(erro)) throw erro
    throw new ErroConsulta('rede')
  }
  if (resposta.status === 503) throw new ErroConsulta('indisponivel')
  if (!resposta.ok) throw new ErroConsulta('interno')
  return (await resposta.json()) as RespostaConsulta
}

export function urlPdf(fonte: FonteSaida): string {
  const url = `${API_URL}${fonte.url_pdf}`
  return fonte.pagina === null ? url : `${url}#page=${fonte.pagina}`
}
