import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { FormularioPergunta } from './FormularioPergunta'

describe('FormularioPergunta', () => {
  it('desabilita o envio com pergunta vazia ou só com espaços', async () => {
    const usuario = userEvent.setup()
    render(<FormularioPergunta carregando={false} aoEnviar={vi.fn()} />)
    const botao = screen.getByRole('button', { name: 'Perguntar' })

    expect(botao).toBeDisabled()
    await usuario.type(screen.getByLabelText('Pergunta'), '   ')
    expect(botao).toBeDisabled()
  })

  it('envia a pergunta sem espaços nas pontas ao clicar', async () => {
    const usuario = userEvent.setup()
    const aoEnviar = vi.fn()
    render(<FormularioPergunta carregando={false} aoEnviar={aoEnviar} />)

    await usuario.type(screen.getByLabelText('Pergunta'), '  O que foi aprovado?  ')
    await usuario.click(screen.getByRole('button', { name: 'Perguntar' }))

    expect(aoEnviar).toHaveBeenCalledExactlyOnceWith('O que foi aprovado?')
  })

  it('envia com Enter e quebra a linha com Shift+Enter', async () => {
    const usuario = userEvent.setup()
    const aoEnviar = vi.fn()
    render(<FormularioPergunta carregando={false} aoEnviar={aoEnviar} />)
    const campo = screen.getByLabelText('Pergunta')

    await usuario.type(campo, 'Linha 1{Shift>}{Enter}{/Shift}Linha 2')
    expect(aoEnviar).not.toHaveBeenCalled()
    expect(campo).toHaveValue('Linha 1\nLinha 2')

    await usuario.type(campo, '{Enter}')
    expect(aoEnviar).toHaveBeenCalledExactlyOnceWith('Linha 1\nLinha 2')
  })

  it('não envia durante o carregamento', async () => {
    const usuario = userEvent.setup()
    const aoEnviar = vi.fn()
    render(<FormularioPergunta carregando={true} aoEnviar={aoEnviar} />)

    await usuario.type(screen.getByLabelText('Pergunta'), 'Pergunta{Enter}')

    expect(screen.getByRole('button', { name: 'Perguntar' })).toBeDisabled()
    expect(aoEnviar).not.toHaveBeenCalled()
  })

  it('limita a pergunta a 1000 caracteres', () => {
    render(<FormularioPergunta carregando={false} aoEnviar={vi.fn()} />)
    expect(screen.getByLabelText('Pergunta')).toHaveAttribute('maxLength', '1000')
  })
})
