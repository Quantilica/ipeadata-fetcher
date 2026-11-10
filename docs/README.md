# Ipeadata (`ipeadata`)

O `ipeadata-fetcher` coleta as séries do Ipeadata, o banco de dados macroeconômicos, regionais e sociais do Instituto de Pesquisa Econômica Aplicada (Ipea), e as converte para o lake em Parquet. O Ipeadata reúne séries produzidas pelo Ipea e por outras instituições (91 fontes no catálogo de 2026-11-05, como IBGE, Banco Central e Anbima).

| Dataset | O que é | Origem (API OData) | Página |
|---|---|---|---|
| `series` | Catálogo de séries: nome, base, fonte, periodicidade, unidade, tema e situação | `Metadados` | [series](datasets/series.md) |
| `temas` | Temas e subtemas das séries | `Temas` | [temas](datasets/temas.md) |
| `territorios` | Territórios dos valores regionais e sociais | `Territorios` | [territorios](datasets/territorios.md) |
| `paises` | Países e regiões das séries macroeconômicas | `Paises` | [paises](datasets/paises.md) |
| `valores` | Valores das séries macroeconômicas | `ValoresSerie` | [valores](datasets/valores.md) |
| `valores_regional` | Valores das séries regionais e sociais, por território | `ValoresSerie` | [valores_regional](datasets/valores_regional.md) |

## Como o Ipeadata publica

- O Ipeadata expõe uma API OData v4 (`http://www.ipeadata.gov.br/api/odata4/`) com cinco entidades: Metadados, Valores, Países, Territórios e Temas. A descrição das colunas está em `http://www.ipeadata.gov.br/api/`.
- Uma série pertence a uma só base (macroeconômica, regional ou social). As macroeconômicas têm um valor por data; as regionais e sociais têm um valor por data e território.
- O fetcher guarda cada resposta da API como JSON. As quatro dimensões (`series`, `temas`, `territorios`, `paises`) ficam em uma pasta com carimbo fixo; os valores têm um arquivo por série.
- O catálogo de 2026-11-05 lista 4.136 séries: 2.510 macroeconômicas (670 inativas), 523 regionais e 1.103 sociais.

## Licença e uso

O termo de Direitos de Uso do Ipeadata (`http://www.ipeadata.gov.br/iframe_direitouso.aspx`) diz que o conteúdo é informação pública que pode ser livremente distribuída e copiada, com a obrigação de citar a fonte Ipeadata. O Ipea não garante a exatidão das informações, que são divulgadas como obtidas nas fontes originais. O termo não detalha condições de cada fonte original.

## Como os conjuntos se relacionam

- `valores` e `valores_regional` se juntam a `series` por `sercodigo`; a unidade (`uninome`) e o multiplicador (`mulnome`) de cada série estão só em `series`.
- `valores_regional` se junta a `territorios` por `nivnome` e `tercodigo`.
- `series.temcodigo` se junta a `temas`; `series.paicodigo`, a `paises`.

## Quebras que valem para mais de um conjunto

| Desde | Mudança | Afeta |
|---|---|---|
| — | A mesma série pode ter arquivos em mais de uma pasta do bruto; o conversor mantém só o de carimbo mais recente (até a 0.3.2, o último em ordem alfabética das pastas substituía os outros; veja os cuidados de `valores`) | `valores`, `valores_regional` |
