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
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respostaHttp(200, resposta)))
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
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))
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
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respostaHttp(status, { detail: 'x' })))
    const usuario = userEvent.setup()
    render(<App />)

    await usuario.type(screen.getByLabelText('Pergunta'), 'Pergunta{Enter}')

    expect(await screen.findByRole('alert')).toHaveTextContent(mensagem)
  })

  it('avisa quando a API está fora do ar', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const usuario = userEvent.setup()
    render(<App />)

    await usuario.type(screen.getByLabelText('Pergunta'), 'Pergunta{Enter}')

    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível conectar à API.')
  })
})
