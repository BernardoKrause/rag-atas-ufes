import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { API_URL, type RespostaConsulta } from './api/consultas'
import App from './App'

const resposta: RespostaConsulta = {
  texto: 'A proposta foi aprovada [1].',
  abstencao: false,
  fontes: [
    {
      numero: 1,
      item_id_canonico: 'ATA_1_PAUTA_1',
      rotulo: 'Ata 1/2024, item 1',
      trecho: 'Aprovada a proposta.',
      pagina: 4,
      url_pdf: '/documentos/9/pdf',
    },
  ],
}

function respostaHttp(status: number, corpo: unknown) {
  return new Response(JSON.stringify(corpo), { status })
}

const orgaos = [{ sigla: 'CCENS_DQF', nome: 'Departamento de Química e Física', atas: 10 }]
const modelos = {
  padrao: 'qwen2.5:7b',
  modelos: [
    { nome: 'qwen2.5:7b', disponivel: true },
    { nome: 'qwen2.5:14b', disponivel: true },
  ],
}

function fetchComOpcoes(consulta: () => Promise<Response>) {
  return vi.fn((url: string) => {
    if (url.endsWith('/orgaos')) return Promise.resolve(respostaHttp(200, orgaos))
    if (url.endsWith('/modelos')) return Promise.resolve(respostaHttp(200, modelos))
    return consulta()
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('mostra o título e a explicação', () => {
    render(<App />)
    expect(screen.getByRole('heading', { level: 1, name: 'Consulta às Atas da UFES' })).toBeInTheDocument()
    expect(
      screen.getByText('Pergunte sobre as atas de reuniões de órgãos colegiados da UFES.'),
    ).toBeInTheDocument()
  })

  it('consulta a API e mostra a resposta com a fonte', async () => {
    vi.stubGlobal('fetch', fetchComOpcoes(() => Promise.resolve(respostaHttp(200, resposta))))
    const usuario = userEvent.setup()
    render(<App />)

    await usuario.type(screen.getByLabelText('Pergunta'), 'O que foi aprovado?{Enter}')

    expect(await screen.findByText(/A proposta foi aprovada/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Abrir PDF' })).toHaveAttribute(
      'href',
      `${API_URL}/documentos/9/pdf#page=4`,
    )
  })

  it('mostra o carregamento enquanto a API responde', async () => {
    vi.stubGlobal('fetch', fetchComOpcoes(() => new Promise(() => {})))
    const usuario = userEvent.setup()
    render(<App />)

    await usuario.type(screen.getByLabelText('Pergunta'), 'O que foi aprovado?{Enter}')

    expect(screen.getByRole('status')).toHaveTextContent('Consultando as atas…')
    expect(screen.getByRole('button', { name: 'Perguntar' })).toBeDisabled()
  })

  it.each([
    [503, 'O serviço de geração está indisponível. Tente novamente em instantes.'],
    [500, 'Ocorreu um erro interno. Tente novamente.'],
  ])('mostra a mensagem do status %i', async (status, mensagem) => {
    vi.stubGlobal('fetch', fetchComOpcoes(() => Promise.resolve(respostaHttp(status, { detail: 'x' }))))
    const usuario = userEvent.setup()
    render(<App />)

    await usuario.type(screen.getByLabelText('Pergunta'), 'Pergunta{Enter}')

    expect(await screen.findByRole('alert')).toHaveTextContent(mensagem)
  })

  it('avisa quando a API está fora do ar', async () => {
    vi.stubGlobal('fetch', fetchComOpcoes(() => Promise.reject(new TypeError('Failed to fetch'))))
    const usuario = userEvent.setup()
    render(<App />)

    await usuario.type(screen.getByLabelText('Pergunta'), 'Pergunta{Enter}')

    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível conectar à API.')
  })

  it('envia o órgão e o modelo escolhidos e mostra a configuração usada', async () => {
    const comConfiguracao = {
      ...resposta,
      configuracao: {
        provedor: 'ollama', modelo: 'qwen2.5:14b', max_tokens: 4096, temperatura: 0, num_ctx: 16384,
        orgao: 'CCENS_DQF', escopo: 'selecao',
      },
    }
    const fetchMock = fetchComOpcoes(() => Promise.resolve(respostaHttp(200, comConfiguracao)))
    vi.stubGlobal('fetch', fetchMock)
    const usuario = userEvent.setup()
    render(<App />)

    await usuario.selectOptions(await screen.findByLabelText('Órgão'), 'CCENS_DQF')
    await usuario.selectOptions(screen.getByLabelText('Modelo de geração'), 'qwen2.5:14b')
    await usuario.type(screen.getByLabelText('Pergunta'), 'O que foi aprovado?{Enter}')

    expect(await screen.findByText('Modelo: qwen2.5:14b · Busca: CCENS / DQF (órgão selecionado)')).toBeInTheDocument()
    const chamada = fetchMock.mock.calls.find(([url]) => url.endsWith('/consultas')) as unknown as [string, RequestInit]
    expect(JSON.parse(chamada[1].body as string)).toEqual({
      pergunta: 'O que foi aprovado?',
      orgao: 'CCENS_DQF',
      modelo: 'qwen2.5:14b',
    })
  })
})
