---
dataset:
  id: "series"
  fonte: "ipeadata"
  titulo: "Séries do Ipeadata (metadados)"
  resumo: "Catálogo das séries do Ipeadata: nome, base, fonte, periodicidade, unidade, tema e situação de cada série."
  orgao: "Instituto de Pesquisa Econômica Aplicada (Ipea)"
  pagina_oficial: "http://www.ipeadata.gov.br/api/"
  licenca: "Termo de Direitos de Uso do Ipeadata: o conteúdo é informação pública que pode ser livremente distribuída e copiada, com obrigação de citar a fonte Ipeadata; sem garantia de exatidão; http://www.ipeadata.gov.br/iframe_direitouso.aspx"
  periodicidade: "atualizada continuamente pelo Ipea; o fetcher guarda um retrato por coleta"
  cobertura: {inicio: "2026-11", fim: "2026-11"}
  unidade: "uma série do Ipeadata"
  granularidade: {espacial: "não se aplica", temporal: "não se aplica"}
  formato_bruto: "JSON da API OData v4 do Ipeadata (`{\"value\": [...]}`), UTF-8, nomes de campo em maiúsculas"
  lake: {estado: convertido, particoes: [], chave: [sercodigo], colunas: 16}
  unidades_de_medida:
    temcodigo: "código do tema (sem unidade)"
  dados_pessoais: "nenhum"
  eras: []
  revisado_em: "2026-11-10"
  versao_fetcher: "0.3.2"
---

# Séries do Ipeadata (metadados)

## Resumo

O catálogo de séries do Ipeadata é a tabela de metadados que descreve cada série de valores: base (macroeconômica, regional ou social), nome, comentário, fonte original, periodicidade, unidade, multiplicador, tema e se ainda é atualizada. É a chave para interpretar `valores` e `valores_regional`: a unidade e o fator de escala de cada série estão aqui, não nos valores.

## Ficha técnica

<!-- gerado:ficha -->

| Campo | Valor |
|---|---|
| Dataset | `ipeadata/series` |
| Órgão | Instituto de Pesquisa Econômica Aplicada (Ipea) |
| Página oficial | http://www.ipeadata.gov.br/api/ |
| Licença | Termo de Direitos de Uso do Ipeadata: o conteúdo é informação pública que pode ser livremente distribuída e copiada, com obrigação de citar a fonte Ipeadata; sem garantia de exatidão; http://www.ipeadata.gov.br/iframe_direitouso.aspx |
| Periodicidade | atualizada continuamente pelo Ipea; o fetcher guarda um retrato por coleta |
| Cobertura | 2026-11 a 2026-11 |
| Unidade (uma linha) | uma série do Ipeadata |
| Granularidade | espacial: não se aplica; temporal: não se aplica |
| Formato bruto | JSON da API OData v4 do Ipeadata (`{"value": [...]}`), UTF-8, nomes de campo em maiúsculas |
| Estado no lake | convertido |
| Partições | — |
| Chave | `sercodigo` |
| Colunas | 16 |
| Unidades de medida | `temcodigo`: código do tema (sem unidade) |
| Dados pessoais | nenhum |
| Eras | nenhuma |
| Revisado em | 2026-11-10 |
| Versão do fetcher | 0.3.2 |

## Origem e coleta

- O fetcher chama a API OData v4 do Ipeadata (`http://www.ipeadata.gov.br/api/odata4/`) e grava a resposta como JSON na pasta `dimensoes/`, com o nome `metadados@20261105.json`. O carimbo é fixo e não é a data da coleta: os endpoints não informam versão, e o carimbo fixo faz o arquivo ser substituído no mesmo lugar quando a dimensão muda.
- O conversor lê a lista `value` do JSON e grava um único Parquet.
- Entidade da API: `Metadados`. O arquivo no Drive tinha 7,5 MB em 2026-11-10.

## Conteúdo

- Uma linha por série. Amostra de 2026-11-10 (arquivo `@20261105`): 4.136 séries, todas com `sercodigo` distinto.
- Por base: 2.510 macroeconômicas (1.840 ativas e 670 inativas), 523 regionais e 1.103 sociais; séries regionais e sociais não têm situação (`serstatus` vazio).
- Por periodicidade (`pernome`): 1.586 mensais, 1.354 anuais, 619 decenais, 469 trimestrais, 51 quadrienais, 38 diárias, 8 `Não se aplica`, 6 irregulares e 5 quinquenais.
- 91 fontes (`fntsigla`) e 65 temas. Última atualização registrada: 2026-11-05.
- Dos arquivos de valores no Drive, 4.138 códigos de série têm arquivo; 4.135 estão no catálogo, e 1 série do catálogo (`ivsc_ivs_capital_humano_p`, base macroeconômica, anual) não tem arquivo de valores.

## Variáveis

| Coluna no lake | Na fonte | Tipo | Descrição | Unidade / códigos | Período |
|---|---|---|---|---|---|
| `sercodigo` | SERCODIGO | texto | Código único da série | ex.: `ABATE12_ABPEBO12` | todo |
| `sernome` | SERNOME | texto | Nome da série, em português | — | todo |
| `sercomentario` | SERCOMENTARIO | texto | Comentários sobre a série, em português; pode conter HTML e tabulações | — | todo |
| `seratualizacao` | SERATUALIZACAO | texto | Data da última carga de dados na série | ISO 8601 com fuso | todo |
| `basnome` | BASNOME | texto | Nome da base de dados da série | Macroeconômico, Regional, Social | todo |
| `fntsigla` | FNTSIGLA | texto | Sigla ou nome abreviado da fonte da série | — | todo |
| `fntnome` | FNTNOME | texto | Nome completo da fonte da série | — | todo |
| `fnturl` | FNTURL | texto | Endereço do site da fonte da série; vazio em 415 séries | — | todo |
| `pernome` | PERNOME | texto | Nome da periodicidade | Diária, Mensal, Trimestral, Anual, Decenal, Quinquenal, Quadrienal, Irregular, Não se aplica | todo |
| `uninome` | UNINOME | texto | Nome da unidade dos valores da série | 70 unidades distintas (ex.: `Tonelada`, `(% PIB)`) | todo |
| `mulnome` | MULNOME | texto | Nome do fator multiplicador dos valores da série; vazio ou espaço quando não há | `mil`, `milhões`, `bilhões`, `centenas`, `centena de milhão`, `centavos` | todo |
| `serstatus` | SERSTATUS | texto | Indica se uma série macroeconômica ainda é atualizada; as regionais e sociais não têm | A = ativa, I = inativa | todo |
| `temcodigo` | TEMCODIGO | inteiro | Código do tema da série | ver dataset `temas` | todo |
| `paicodigo` | PAICODIGO | texto | País ou região da série; só vale para séries macroeconômicas (vazio em 492 séries) | `BRA`, `USA`, `WRLD`; ver `paises` | todo |
| `sernumerica` | SERNUMERICA | booleano | Indica se a série tem valores numéricos (verdadeiro) ou alfanuméricos (falso) | todas verdadeiras na amostra | todo |
| `ativa` | — (gerada) | booleano | Série ativa: verdadeiro quando `serstatus` é `A` ou vazio (regionais e sociais contam como ativas); falso para `I` | 3.466 verdadeiras e 670 falsas na amostra | todo |

## No lake

- Dataset `ipeadata/series`, sem partição: um Parquet `metadados.parquet`.
- Chave natural (amostra): `sercodigo`, sem repetição.
- O conversor lê `value`, normaliza o nome das colunas (minúsculas, sem acento) e infere tipos: `temcodigo` é inteiro e `sernumerica` é booleano; o resto é texto, inclusive `seratualizacao` (data em texto).
- Acrescenta `ativa` a partir de `serstatus`.
- A API do Ipeadata documenta um campo `PAICODIGO` e um `SERNUMERICA` bit; ambos chegam como estão.

## Cuidados de uso

- **Unidade e escala moram aqui.** `valores.valor` vem como a fonte publicou; para saber se é R$ mil, milhões ou índice, consulte `uninome` e `mulnome` da série. Não compare séries sem isso.
- **`mulnome` com espaço.** 164 séries têm `mulnome` igual a um espaço em branco e 2.891 têm nulo (conferido em 2026-11-10); trate os dois como "sem multiplicador".
- **Inativas.** 670 séries macroeconômicas têm `serstatus = I`: não são mais atualizadas. Séries regionais e sociais não têm essa informação e `ativa` as marca como verdadeiras mesmo sem atualização garantida.
- **Séries de terceiros.** `fntnome` mostra a fonte original (91 fontes). O termo de uso do Ipeadata não detalha condições por fonte; a verificação por série não foi feita.
- **Sem arquivo de valores.** O catálogo tem séries sem valores no bruto (1 em 2026-11-10).
- **Retrato, sem histórico.** A dimensão é a lista vigente na data da coleta (2026-11-05); mudanças anteriores não ficam registradas.
- **Nomes de coluna.** O conversor passa o nome do campo da API para minúsculas, sem acento (`SERNOME` vira `sernome`).

## Exemplos

Séries macroeconômicas ativas mensais de fontes IBGE, com unidade e multiplicador:

```python
import duckdb

duckdb.sql("""
    SELECT sercodigo, sernome, uninome, mulnome
    FROM read_parquet('lake/ipeadata/series/*.parquet')
    WHERE basnome = 'Macroeconômico' AND ativa AND pernome = 'Mensal' AND fntsigla LIKE 'IBGE%'
    ORDER BY sercodigo
    LIMIT 20
""").show()
```

## Referências

- API do Ipeadata (descrição das entidades e colunas): http://www.ipeadata.gov.br/api/
- Direitos de uso: http://www.ipeadata.gov.br/iframe_direitouso.aspx
- Ipeadata: http://www.ipeadata.gov.br
