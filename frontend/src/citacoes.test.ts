import { describe, expect, it } from 'vitest'
import { dividirCitacoes } from './citacoes'

describe('dividirCitacoes', () => {
  it('devolve texto sem marcadores como um único trecho', () => {
    expect(dividirCitacoes('Sem citações.', new Set([1]))).toEqual([{ tipo: 'texto', conteudo: 'Sem citações.' }])
  })

  it('separa as citações válidas do texto', () => {
    expect(dividirCitacoes('Aprovado [1] e homologado [2].', new Set([1, 2]))).toEqual([
      { tipo: 'texto', conteudo: 'Aprovado ' },
      { tipo: 'citacao', numero: 1 },
      { tipo: 'texto', conteudo: ' e homologado ' },
      { tipo: 'citacao', numero: 2 },
      { tipo: 'texto', conteudo: '.' },
    ])
  })

  it('separa citações coladas', () => {
    expect(dividirCitacoes('Aprovado [1][2]', new Set([1, 2]))).toEqual([
      { tipo: 'texto', conteudo: 'Aprovado ' },
      { tipo: 'citacao', numero: 1 },
      { tipo: 'citacao', numero: 2 },
    ])
  })

  it('mantém como texto um marcador sem fonte', () => {
    expect(dividirCitacoes('Aprovado [3] e [1].', new Set([1]))).toEqual([
      { tipo: 'texto', conteudo: 'Aprovado [3] e ' },
      { tipo: 'citacao', numero: 1 },
      { tipo: 'texto', conteudo: '.' },
    ])
  })

  it('devolve lista vazia para texto vazio', () => {
    expect(dividirCitacoes('', new Set())).toEqual([])
  })
})
