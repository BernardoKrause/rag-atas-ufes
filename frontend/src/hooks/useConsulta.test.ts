import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { consultar, ErroConsulta, type RespostaConsulta } from '../api/consultas'
import { useConsulta } from './useConsulta'

vi.mock('../api/consultas', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/consultas')>()),
  consultar: vi.fn(),
}))

const consultarMock = vi.mocked(consultar)

const resposta: RespostaConsulta = { texto: 'Foi aprovado.', abstencao: false, fontes: [] }

beforeEach(() => {
  consultarMock.mockReset()
})

describe('useConsulta', () => {
  it('começa ocioso', () => {
    const { result } = renderHook(() => useConsulta())
    expect(result.current.estado).toEqual({ fase: 'ocioso' })
  })

  it('passa por carregando e termina em sucesso', async () => {
    let resolver: (valor: RespostaConsulta) => void = () => {}
    consultarMock.mockReturnValue(new Promise<RespostaConsulta>((r) => (resolver = r)))
    const { result } = renderHook(() => useConsulta())

    act(() => {
      void result.current.perguntar('pergunta')
    })
    expect(result.current.estado).toEqual({ fase: 'carregando' })

    await act(async () => resolver(resposta))
    expect(result.current.estado).toEqual({ fase: 'sucesso', resposta })
    expect(consultarMock).toHaveBeenCalledWith('pergunta', expect.any(AbortSignal), {})
  })

  it('termina em erro com o tipo do ErroConsulta', async () => {
    consultarMock.mockRejectedValue(new ErroConsulta('indisponivel'))
    const { result } = renderHook(() => useConsulta())

    await act(() => result.current.perguntar('pergunta'))

    expect(result.current.estado).toEqual({ fase: 'erro', tipo: 'indisponivel' })
  })

  it('trata erro desconhecido como interno', async () => {
    consultarMock.mockRejectedValue(new Error('inesperado'))
    const { result } = renderHook(() => useConsulta())

    await act(() => result.current.perguntar('pergunta'))

    expect(result.current.estado).toEqual({ fase: 'erro', tipo: 'interno' })
  })

  it('cancela a pergunta anterior e fica com a resposta da nova', async () => {
    consultarMock.mockImplementationOnce(
      (_pergunta, sinal) =>
        new Promise<RespostaConsulta>((_resolver, rejeitar) => {
          sinal?.addEventListener('abort', () => rejeitar(new DOMException('Aborted', 'AbortError')))
        }),
    )
    consultarMock.mockResolvedValueOnce(resposta)
    const { result } = renderHook(() => useConsulta())

    act(() => {
      void result.current.perguntar('primeira')
    })
    await act(() => result.current.perguntar('segunda'))

    expect(consultarMock.mock.calls[0][1]?.aborted).toBe(true)
    await waitFor(() => expect(result.current.estado).toEqual({ fase: 'sucesso', resposta }))
  })

  it('ignora a resposta de uma pergunta já cancelada', async () => {
    let resolverPrimeira: (valor: RespostaConsulta) => void = () => {}
    consultarMock.mockReturnValueOnce(new Promise<RespostaConsulta>((r) => (resolverPrimeira = r)))
    consultarMock.mockRejectedValueOnce(new ErroConsulta('rede'))
    const { result } = renderHook(() => useConsulta())

    act(() => {
      void result.current.perguntar('primeira')
    })
    await act(() => result.current.perguntar('segunda'))
    await act(async () => resolverPrimeira(resposta))

    expect(result.current.estado).toEqual({ fase: 'erro', tipo: 'rede' })
  })
})
