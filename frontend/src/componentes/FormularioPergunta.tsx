import { useState } from 'react'
import { rotuloOrgao, type Modelos, type OpcoesConsulta, type Orgao } from '../api/consultas'

const LIMITE_CARACTERES = 1000
const CLASSE_SELETOR =
  'rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-900 focus:border-blue-500 focus:ring-2 focus:ring-blue-200 focus:outline-none'

type Props = {
  carregando: boolean
  aoEnviar: (pergunta: string, opcoes: OpcoesConsulta) => void
  orgaos?: Orgao[]
  modelos?: Modelos | null
}

export function FormularioPergunta({ carregando, aoEnviar, orgaos = [], modelos = null }: Props) {
  const [pergunta, setPergunta] = useState('')
  const [orgao, setOrgao] = useState('')
  const [modelo, setModelo] = useState('')
  const vazia = pergunta.trim() === ''
  const modeloEscolhido = modelo || modelos?.padrao || ''

  function enviar() {
    if (vazia || carregando) return
    const opcoes: OpcoesConsulta = {}
    if (orgao) opcoes.orgao = orgao
    if (modelos && modeloEscolhido && modeloEscolhido !== modelos.padrao) opcoes.modelo = modeloEscolhido
    aoEnviar(pergunta.trim(), opcoes)
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
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap gap-3">
          {orgaos.length > 0 && (
            <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
              Órgão
              <select value={orgao} onChange={(evento) => setOrgao(evento.target.value)} className={CLASSE_SELETOR}>
                <option value="">Todo o acervo</option>
                {orgaos.map((item) => (
                  <option key={item.sigla} value={item.sigla}>
                    {rotuloOrgao(item)}
                  </option>
                ))}
              </select>
            </label>
          )}
          {modelos && modelos.modelos.length > 0 && (
            <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
              Modelo de geração
              <select
                value={modeloEscolhido}
                onChange={(evento) => setModelo(evento.target.value)}
                className={CLASSE_SELETOR}
              >
                {modelos.modelos.map((item) => (
                  <option key={item.nome} value={item.nome} disabled={!item.disponivel}>
                    {item.nome}
                    {item.nome === modelos.padrao ? ' (padrão)' : ''}
                    {item.disponivel ? '' : ' (indisponível)'}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
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
