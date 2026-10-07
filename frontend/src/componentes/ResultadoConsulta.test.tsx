import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { API_URL, type RespostaConsulta } from '../api/consultas'
import { ResultadoConsulta } from './ResultadoConsulta'

const resposta: RespostaConsulta = {
  texto: 'O conselho aprovou a proposta [1] e designou a comissão [2].',
  abstencao: false,
  fontes: [
    {
      numero: 1,
      item_id_canonico: 'ATA_1_PAUTA_1',
      rotulo: 'Ata 1/2024, item 1',
      trecho: 'Aprovada a proposta.',
      pagina: 2,
      url_pdf: '/documentos/5/pdf',
    },
    {
      numero: 2,
      item_id_canonico: 'ATA_1_PAUTA_2',
      rotulo: 'Ata 1/2024, item 2',
      trecho: 'Designada a comissão.',
      pagina: null,
      url_pdf: '/documentos/5/pdf',
    },
  ],
}

afterEach(() => {
  vi.useRealTimers()
})

describe('ResultadoConsulta', () => {
  it('mostra o texto com as citações como botões', () => {
    render(<ResultadoConsulta resposta={resposta} />)

    expect(screen.getByRole('button', { name: 'Ver fonte 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ver fonte 2' })).toBeInTheDocument()
    expect(screen.getByText(/O conselho aprovou a proposta/)).toBeInTheDocument()
  })

  it('lista as fontes com rótulo, trecho, página e link do PDF', () => {
    render(<ResultadoConsulta resposta={resposta} />)

    const primeira = document.getElementById('fonte-1')!
    expect(within(primeira).getByText(/Ata 1\/2024, item 1/)).toBeInTheDocument()
    expect(within(primeira).getByText('Aprovada a proposta.')).toBeInTheDocument()
    expect(within(primeira).getByText('p. 2')).toBeInTheDocument()
    const link = within(primeira).getByRole('link', { name: 'Abrir PDF' })
    expect(link).toHaveAttribute('href', `${API_URL}/documentos/5/pdf#page=2`)
    expect(link).toHaveAttribute('target', '_blank')

    const segunda = document.getElementById('fonte-2')!
    expect(within(segunda).queryByText(/^p\./)).not.toBeInTheDocument()
    expect(within(segunda).getByRole('link', { name: 'Abrir PDF' })).toHaveAttribute(
      'href',
      `${API_URL}/documentos/5/pdf`,
    )
  })

  it('rola até a fonte citada e a destaca por 2 segundos', () => {
    vi.useFakeTimers()
    render(<ResultadoConsulta resposta={resposta} />)
    const segunda = document.getElementById('fonte-2')!

    fireEvent.click(screen.getByRole('button', { name: 'Ver fonte 2' }))

    expect(segunda.scrollIntoView).toHaveBeenCalled()
    expect(segunda).toHaveAttribute('data-destacada', 'true')
    expect(document.getElementById('fonte-1')).toHaveAttribute('data-destacada', 'false')

    act(() => {
      vi.advanceTimersByTime(2000)
    })
    expect(segunda).toHaveAttribute('data-destacada', 'false')
  })

  it('mostra a abstenção como aviso e sem lista de fontes', () => {
    const abstencao: RespostaConsulta = {
      texto: 'Não encontrei nas atas disponíveis informação suficiente para responder a essa pergunta.',
      abstencao: true,
      fontes: [],
    }
    render(<ResultadoConsulta resposta={abstencao} />)

    expect(screen.getByRole('status')).toHaveTextContent('Não encontrei nas atas disponíveis')
    expect(screen.queryByRole('heading', { name: 'Fontes' })).not.toBeInTheDocument()
  })
})
