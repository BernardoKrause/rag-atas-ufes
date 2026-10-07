import { useState } from 'react'

const LIMITE_CARACTERES = 1000

type Props = {
  carregando: boolean
  aoEnviar: (pergunta: string) => void
}

export function FormularioPergunta({ carregando, aoEnviar }: Props) {
  const [pergunta, setPergunta] = useState('')
  const vazia = pergunta.trim() === ''

  function enviar() {
    if (vazia || carregando) return
    aoEnviar(pergunta.trim())
  }

  return (
    <form
      className="space-y-3"
      onSubmit={(evento) => {
        evento.preventDefault()
        enviar()
      }}
    >
      <label htmlFor="pergunta" className="sr-only">
        Pergunta
      </label>
      <textarea
        id="pergunta"
        value={pergunta}
        maxLength={LIMITE_CARACTERES}
        rows={3}
        placeholder="Ex.: O que foi deliberado sobre afastamentos para pós-graduação?"
        onChange={(evento) => setPergunta(evento.target.value)}
        onKeyDown={(evento) => {
          if (evento.key === 'Enter' && !evento.shiftKey && !evento.nativeEvent.isComposing) {
            evento.preventDefault()
            enviar()
          }
        }}
        className="w-full resize-y rounded-lg border border-slate-300 bg-white p-3 text-slate-900 focus:border-blue-500 focus:ring-2 focus:ring-blue-200 focus:outline-none"
      />
      <div className="flex justify-end">
        <button
          type="submit"
          disabled={vazia || carregando}
          className="rounded-lg bg-blue-700 px-4 py-2 font-medium text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          Perguntar
        </button>
      </div>
    </form>
  )
}
