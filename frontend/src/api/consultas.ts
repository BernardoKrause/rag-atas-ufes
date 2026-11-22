export interface FonteSaida {
  numero: number
  item_id_canonico: string
  rotulo: string
  trecho: string
  pagina: number | null
  url_pdf: string
}

export interface Configuracao {
  provedor: string
  modelo: string
  max_tokens: number
  temperatura?: number | null
  num_ctx?: number | null
  orgao: string | null
  escopo: 'selecao' | 'pergunta' | 'acervo'
}

export interface RespostaConsulta {
  texto: string
  abstencao: boolean
  fontes: FonteSaida[]
  configuracao?: Configuracao
}

export interface OpcoesConsulta {
  orgao?: string
  modelo?: string
}

export interface Orgao {
  sigla: string
  nome: string | null
  atas: number
}

export interface Modelo {
  nome: string
  disponivel: boolean
}

export interface Modelos {
  padrao: string
  modelos: Modelo[]
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

export const API_URL: string = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/+$/, '')

export function ehCancelamento(erro: unknown): boolean {
  return typeof erro === 'object' && erro !== null && (erro as { name?: unknown }).name === 'AbortError'
}

export async function consultar(
  pergunta: string,
  signal?: AbortSignal,
  opcoes: OpcoesConsulta = {},
): Promise<RespostaConsulta> {
  let resposta: Response
  try {
    resposta = await fetch(`${API_URL}/consultas`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pergunta, ...opcoes }),
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

async function obter<T>(caminho: string, signal?: AbortSignal): Promise<T> {
  const resposta = await fetch(`${API_URL}${caminho}`, { signal })
  if (!resposta.ok) throw new ErroConsulta('interno')
  return (await resposta.json()) as T
}

export function listarOrgaos(signal?: AbortSignal): Promise<Orgao[]> {
  return obter<Orgao[]>('/orgaos', signal)
}

export function listarModelos(signal?: AbortSignal): Promise<Modelos> {
  return obter<Modelos>('/modelos', signal)
}

export function rotuloOrgao(orgao: Orgao): string {
  const sigla = orgao.sigla.replaceAll('_', ' / ')
  return orgao.nome ? `${orgao.nome} (${sigla})` : sigla
}

export function urlPdf(fonte: FonteSaida): string {
  const url = `${API_URL}${fonte.url_pdf}`
  return fonte.pagina === null ? url : `${url}#page=${fonte.pagina}`
}
