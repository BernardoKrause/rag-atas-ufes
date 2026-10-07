import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  API_URL,
  consultar,
  ehCancelamento,
  ErroConsulta,
  urlPdf,
  type FonteSaida,
  type RespostaConsulta,
  type TipoErroConsulta,
} from './consultas'

const fonte: FonteSaida = {
  numero: 1,
  item_id_canonico: 'ATA_1_PAUTA_2',
  rotulo: 'Ata 1/2024, item 2',
  trecho: 'Aprovado por unanimidade.',
  pagina: 3,
  url_pdf: '/documentos/7/pdf',
}

const resposta: RespostaConsulta = { texto: 'Foi aprovado [1].', abstencao: false, fontes: [fonte] }

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('consultar', () => {
  it('envia a pergunta por POST em JSON e devolve a resposta', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(resposta), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const sinal = new AbortController().signal

    await expect(consultar('O que foi aprovado?', sinal)).resolves.toEqual(resposta)
    expect(fetchMock).toHaveBeenCalledWith(`${API_URL}/consultas`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pergunta: 'O que foi aprovado?' }),
      signal: sinal,
    })
  })

  it.each([
    [503, 'indisponivel'],
    [500, 'interno'],
    [422, 'interno'],
  ] as [number, TipoErroConsulta][])('converte o status %i no erro %s', async (status, tipo) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status })))

    const promessa = consultar('pergunta')

    await expect(promessa).rejects.toBeInstanceOf(ErroConsulta)
    await expect(promessa).rejects.toMatchObject({ tipo })
  })

  it('converte falha de conexão no erro rede', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(consultar('pergunta')).rejects.toMatchObject({ tipo: 'rede' })
  })

  it('repassa o cancelamento sem convertê-lo', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('Aborted', 'AbortError')))

    const promessa = consultar('pergunta')

    await expect(promessa).rejects.toMatchObject({ name: 'AbortError' })
    await expect(promessa).rejects.not.toBeInstanceOf(ErroConsulta)
  })
})

describe('ehCancelamento', () => {
  it('reconhece só o AbortError', () => {
    expect(ehCancelamento(new DOMException('Aborted', 'AbortError'))).toBe(true)
    expect(ehCancelamento(new ErroConsulta('rede'))).toBe(false)
    expect(ehCancelamento(null)).toBe(false)
  })
})

describe('urlPdf', () => {
  it('aponta para a página citada', () => {
    expect(urlPdf(fonte)).toBe(`${API_URL}/documentos/7/pdf#page=3`)
  })

  it('omite a página quando ela é desconhecida', () => {
    expect(urlPdf({ ...fonte, pagina: null })).toBe(`${API_URL}/documentos/7/pdf`)
  })
})
