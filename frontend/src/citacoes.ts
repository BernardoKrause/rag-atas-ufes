export type Trecho = { tipo: 'texto'; conteudo: string } | { tipo: 'citacao'; numero: number }

export function dividirCitacoes(texto: string, numerosValidos: Set<number>): Trecho[] {
  const trechos: Trecho[] = []
  let inicio = 0
  for (const marcador of texto.matchAll(/\[(\d+)\]/g)) {
    const numero = Number(marcador[1])
    if (!numerosValidos.has(numero)) continue
    if (marcador.index > inicio) trechos.push({ tipo: 'texto', conteudo: texto.slice(inicio, marcador.index) })
    trechos.push({ tipo: 'citacao', numero })
    inicio = marcador.index + marcador[0].length
  }
  if (inicio < texto.length) trechos.push({ tipo: 'texto', conteudo: texto.slice(inicio) })
  return trechos
}
