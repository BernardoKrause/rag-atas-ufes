# Anonimização: o que é substituído e por quê

O texto de cada ata é anonimizado antes de ser segmentado, indexado e enviado ao LLM (`backend/app/ingestion/cleaner.py`). Cada entidade vira um token determinístico (`PESSOA_n`, `CPF_n`...): a mesma entidade real gera sempre o mesmo token, em qualquer ata.

O TCC1 pede a anonimização de nomes e números de processo. Os outros tipos entraram porque, ao lado de um `PESSOA_n` estável, um identificador pessoal revela quem é a pessoa em todas as atas e desfaz a pseudonimização.

## Tipos anonimizados

| Tipo | Como é detectado |
|---|---|
| `PESSOA` | NER (`Gpaiva/NERDE-base`) |
| `PROCESSO` | `NNNNN.NNNNNN/NNNN-NN`, tolerando espaço ou quebra de linha |
| `CPF` | Com pontuação; ou 11 dígitos com dígito verificador válido; ou 11 dígitos logo após a palavra "CPF" ou logo após um nome, mesmo com dígito verificador errado (erro de digitação na ata) |
| `RG` | Número após "RG" ou "Identidade" |
| `EMAIL` | Qualquer e-mail, exceto a lista de endereços institucionais em `EMAILS_INSTITUCIONAIS` |
| `SIAPE` | Número após "SIAPE" |
| `MATRICULA` | Número após "matrícula", "matrícula UFES" ou "matr:" |
| `LINK_PESSOAL` | Currículo Lattes e sala pessoal do conferenciaweb (o endereço contém o nome da pessoa) |
| `TELEFONE` | Celular: `9XXXX-XXXX`, com ou sem DDD |

## Decisões

- **Telefone (2026-10-06): só o celular é anonimizado.** No corpus de 357 atas aparecem 4 celulares, todos de estudantes (doc 1894). Os números fixos (`XXXX-XXXX`) são das secretarias e departamentos, não identificam uma pessoa e ficam no texto. A regra exige o formato de celular (nove dígitos começando com 9, com separador), o que também deixa de fora intervalos de anos como "2016-2020".
- **Palavra-chave antes do número.** SIAPE, matrícula e RG só são anonimizados com o número logo após a palavra-chave. Assim, frases como "informar nome completo, SIAPE e telefone" ficam intactas.
- **Dígito verificador do CPF.** Onze dígitos soltos só viram CPF com dígito verificador válido, porque o corpus tem ISBNs e hashes de 11 dígitos. A exceção é o contexto forte (a palavra "CPF" ou um nome logo antes). Nesse caso o número é anonimizado mesmo com dígito verificador errado, já que os 9 primeiros dígitos continuam sendo o CPF real.

## Limitações conhecidas

- Matrícula sem palavra-chave (por exemplo, numa coluna de tabela) não é detectada.
- Formatos raros fora dos padrões acima passam: link do conferenciaweb em `/webconf/`, RG de 7 dígitos sem dígito verificador.
- Mudar as regras não altera atas já processadas. É preciso reprocessar o corpus (Parte 10).
