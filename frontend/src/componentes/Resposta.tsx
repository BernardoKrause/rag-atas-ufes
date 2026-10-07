import { Fragment } from 'react'
import type { RespostaConsulta } from '../api/consultas'
import { dividirCitacoes } from '../citacoes'

type Props = {
  resposta: RespostaConsulta
  aoCitar: (numero: number) => void
}

export function Resposta({ resposta, aoCitar }: Props) {
  if (resposta.abstencao) {
    return (
      <p role="status" className="rounded-lg border border-slate-300 bg-slate-100 p-4 text-slate-700">
        {resposta.texto}
      </p>
    )
  }

  const numeros = new Set(resposta.fontes.map((fonte) => fonte.numero))
  return (
    <p className="whitespace-pre-line leading-relaxed text-slate-800">
      {dividirCitacoes(resposta.texto, numeros).map((trecho, indice) =>
        trecho.tipo === 'texto' ? (
          <Fragment key={indice}>{trecho.conteudo}</Fragment>
        ) : (
          <button
            key={indice}
            type="button"
            aria-label={`Ver fonte ${trecho.numero}`}
            onClick={() => aoCitar(trecho.numero)}
            className="mx-0.5 rounded px-1 text-sm font-semibold text-blue-700 hover:bg-blue-50"
          >
            [{trecho.numero}]
          </button>
        ),
      )}
    </p>
  )
}
