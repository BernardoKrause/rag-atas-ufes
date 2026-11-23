import { useCallback, useEffect, useRef, useState } from 'react'
import {
  consultar,
  ehCancelamento,
  ErroConsulta,
  type OpcoesConsulta,
  type RespostaConsulta,
  type TipoErroConsulta,
} from '../api/consultas'

export type EstadoConsulta =
  | { fase: 'ocioso' }
  | { fase: 'carregando' }
  | { fase: 'sucesso'; resposta: RespostaConsulta }
  | { fase: 'erro'; tipo: TipoErroConsulta }

export function useConsulta() {
  const [estado, setEstado] = useState<EstadoConsulta>({ fase: 'ocioso' })
  const controladorRef = useRef<AbortController | null>(null)

  useEffect(() => () => controladorRef.current?.abort(), [])

  const perguntar = useCallback(async (pergunta: string, opcoes: OpcoesConsulta = {}) => {
    controladorRef.current?.abort()
    const controlador = new AbortController()
    controladorRef.current = controlador
    setEstado({ fase: 'carregando' })
    try {
      const resposta = await consultar(pergunta, controlador.signal, opcoes)
      if (controlador.signal.aborted) return
      setEstado({ fase: 'sucesso', resposta })
    } catch (erro) {
      if (controlador.signal.aborted || ehCancelamento(erro)) return
      setEstado({ fase: 'erro', tipo: erro instanceof ErroConsulta ? erro.tipo : 'interno' })
    }
  }, [])

  return { estado, perguntar }
}
