# Fixtures dos testes

Os PDFs de `atas_sample/` e `ocr/` são sintéticos: o texto é inventado e reproduz só a estrutura de cada formato de ata (cabeçalhos e rodapés repetidos, numeração dos itens de cada órgão, marca d'água de ata em aprovação, ligadura quebrada, numeração de linhas na margem, página digitalizada e texto vetorizado). Nenhum trecho, nome ou número vem de uma ata real, e as atas do corpus não ficam no repositório.

Para gerar de novo, a partir de `backend/`:

```bash
python tests/fixtures/gerar_sinteticos.py "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
```

O texto usa a Helvetica padrão do PDF. A fonte passada como argumento só entra, como subconjunto, na linha com o glifo U+019F (Ɵ), que simula a ligadura "ti" quebrada.
