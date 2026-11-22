import { FormularioPergunta } from './componentes/FormularioPergunta'
import { MensagemErro } from './componentes/MensagemErro'
import { ResultadoConsulta } from './componentes/ResultadoConsulta'
import { useConsulta } from './hooks/useConsulta'
import { useOpcoes } from './hooks/useOpcoes'

export default function App() {
  const { estado, perguntar } = useConsulta()
  const { orgaos, modelos } = useOpcoes()

  return (
    <div className="min-h-screen bg-slate-50">
      <main className="mx-auto max-w-3xl space-y-6 px-4 py-10">
        <header className="space-y-1">
          <h1 className="text-2xl font-bold text-slate-900">Consulta às Atas da UFES</h1>
          <p className="text-slate-600">Pergunte sobre as atas de reuniões de órgãos colegiados da UFES.</p>
        </header>
        <FormularioPergunta
          carregando={estado.fase === 'carregando'}
          aoEnviar={perguntar}
          orgaos={orgaos}
          modelos={modelos}
        />
        {estado.fase === 'carregando' && (
          <p role="status" className="text-slate-600">
            Consultando as atas…
          </p>
        )}
        {estado.fase === 'erro' && <MensagemErro tipo={estado.tipo} />}
        {estado.fase === 'sucesso' && <ResultadoConsulta resposta={estado.resposta} />}
      </main>
    </div>
  )
}
