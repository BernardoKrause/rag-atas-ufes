import { useEffect, useState } from 'react'
import { listarModelos, listarOrgaos, type Modelos, type Orgao } from '../api/consultas'

export function useOpcoes() {
  const [orgaos, setOrgaos] = useState<Orgao[]>([])
  const [modelos, setModelos] = useState<Modelos | null>(null)

  useEffect(() => {
    const controlador = new AbortController()
    listarOrgaos(controlador.signal).then((lista) => Array.isArray(lista) && setOrgaos(lista), () => {})
    listarModelos(controlador.signal).then(setModelos, () => {})
    return () => controlador.abort()
  }, [])

  return { orgaos, modelos }
}
