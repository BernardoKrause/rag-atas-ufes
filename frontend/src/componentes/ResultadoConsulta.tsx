import { useEffect, useRef, useState } from 'react'
import type { Configuracao, RespostaConsulta } from '../api/consultas'
import { ListaFontes } from './ListaFontes'
import { Resposta } from './Resposta'

const DURACAO_DESTAQUE_MS = 2000

const DESCRICAO_ESCOPO: Record<Configuracao['escopo'], string> = {
  selecao: 'órgão selecionado',
  pergunta: 'órgão citado na pergunta',
  acervo: 'todo o acervo',
}

function textoConfiguracao(configuracao: Configuracao): string {
  const escopo = DESCRICAO_ESCOPO[configuracao.escopo]
  const busca = configuracao.orgao ? `${configuracao.orgao.replaceAll('_', ' / ')} (${escopo})` : escopo
  return `Modelo: ${configuracao.modelo} · Busca: ${busca}`
}

export function ResultadoConsulta({ resposta }: { resposta: RespostaConsulta }) {
  const [destacada, setDestacada] = useState<number | null>(null)
  const temporizador = useRef<number | undefined>(undefined)

  useEffect(() => () => window.clearTimeout(temporizador.current), [])

  function citar(numero: number) {
    document.getElementById(`fonte-${numero}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    setDestacada(numero)
    window.clearTimeout(temporizador.current)
    temporizador.current = window.setTimeout(() => setDestacada(null), DURACAO_DESTAQUE_MS)
  }

  return (
    <div className="space-y-6">
      <Resposta resposta={resposta} aoCitar={citar} />
      {resposta.configuracao && (
        <p className="text-xs text-slate-500">{textoConfiguracao(resposta.configuracao)}</p>
      )}
      {!resposta.abstencao && resposta.fontes.length > 0 && (
        <ListaFontes fontes={resposta.fontes} destacada={destacada} />
      )}
    </div>
  )
}
