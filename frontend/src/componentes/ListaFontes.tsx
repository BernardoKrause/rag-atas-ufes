import { urlPdf, type FonteSaida } from '../api/consultas'

type Props = {
  fontes: FonteSaida[]
  destacada: number | null
}

export function ListaFontes({ fontes, destacada }: Props) {
  return (
    <section aria-labelledby="titulo-fontes" className="space-y-3">
      <h2 id="titulo-fontes" className="text-lg font-semibold text-slate-900">
        Fontes
      </h2>
      <ol className="space-y-3">
        {fontes.map((fonte) => {
          const estaDestacada = fonte.numero === destacada
          return (
            <li
              key={fonte.numero}
              id={`fonte-${fonte.numero}`}
              data-destacada={estaDestacada}
              className={`rounded-lg border p-4 transition-colors ${
                estaDestacada ? 'border-blue-500 bg-blue-50' : 'border-slate-200 bg-white'
              }`}
            >
              <div className="flex items-baseline justify-between gap-4">
                <p className="font-medium text-slate-900">
                  [{fonte.numero}] {fonte.rotulo}
                </p>
                {fonte.pagina !== null && <span className="shrink-0 text-sm text-slate-500">p. {fonte.pagina}</span>}
              </div>
              <p className="mt-2 text-sm text-slate-700">{fonte.trecho}</p>
              <a
                href={urlPdf(fonte)}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-3 inline-block text-sm font-medium text-blue-700 hover:underline"
              >
                Abrir PDF
              </a>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
