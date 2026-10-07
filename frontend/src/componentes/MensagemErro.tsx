import type { TipoErroConsulta } from '../api/consultas'

const MENSAGENS: Record<TipoErroConsulta, string> = {
  indisponivel: 'O serviço de geração está indisponível. Tente novamente em instantes.',
  interno: 'Ocorreu um erro interno. Tente novamente.',
  rede: 'Não foi possível conectar à API.',
}

export function MensagemErro({ tipo }: { tipo: TipoErroConsulta }) {
  return (
    <p role="alert" className="rounded-lg border border-red-300 bg-red-50 p-4 text-red-800">
      {MENSAGENS[tipo]}
    </p>
  )
}
