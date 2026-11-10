---
dataset:
  id: "valores_regional"
  fonte: "ipeadata"
  titulo: "Valores das séries regionais e sociais do Ipeadata"
  resumo: "Observações (data, território e valor) das séries regionais e sociais do Ipeadata, uma linha por série, data e território."
  orgao: "Instituto de Pesquisa Econômica Aplicada (Ipea)"
  pagina_oficial: "http://www.ipeadata.gov.br/api/"
  licenca: "Termo de Direitos de Uso do Ipeadata: o conteúdo é informação pública que pode ser livremente distribuída e copiada, com obrigação de citar a fonte Ipeadata; sem garantia de exatidão; http://www.ipeadata.gov.br/iframe_direitouso.aspx"
  periodicidade: "varia por série (trimestral a decenal na amostra; ver `series.pernome`)"
  cobertura: {inicio: "1985", fim: "em-curso"}
  unidade: "valor de uma série regional ou social em uma data e um território"
  granularidade: {espacial: "Brasil, regiões, estados, municípios e outros níveis (AMC, mesorregião, microrregião, área metropolitana)", temporal: "da data da observação: trimestre a década, conforme a série"}
  formato_bruto: "JSON da API OData v4 do Ipeadata (função `ValoresSerie`), um arquivo por série; um arquivo mistura vários níveis territoriais"
  lake: {estado: convertido, particoes: [nivel, periodicidade], chave: [sercodigo, valdata, nivnome, tercodigo], colunas: 7}
  unidades_de_medida:
    valvalor: "varia por série (series.uninome e series.mulnome)"
    valor: "varia por série (series.uninome e series.mulnome)"
  dados_pessoais: "nenhum"
  eras: []
  revisado_em: "2026-11-10"
  versao_fetcher: "0.3.2"
---

# Valores das séries regionais e sociais do Ipeadata

## Resumo

Valores das séries regionais (por exemplo, agências bancárias e despesas dos entes) e sociais (por exemplo, índices de desenvolvimento humano e dados da PNAD Contínua) do Ipeadata. Cada linha traz o território em `nivnome` e `tercodigo`, que se juntam à tabela `territorios`.

## Ficha técnica

<!-- gerado:ficha -->

| Campo | Valor |
|---|---|
| Dataset | `ipeadata/valores_regional` |
| Órgão | Instituto de Pesquisa Econômica Aplicada (Ipea) |
| Página oficial | http://www.ipeadata.gov.br/api/ |
| Licença | Termo de Direitos de Uso do Ipeadata: o conteúdo é informação pública que pode ser livremente distribuída e copiada, com obrigação de citar a fonte Ipeadata; sem garantia de exatidão; http://www.ipeadata.gov.br/iframe_direitouso.aspx |
| Periodicidade | varia por série (trimestral a decenal na amostra; ver `series.pernome`) |
| Cobertura | 1985 a em-curso |
| Unidade (uma linha) | valor de uma série regional ou social em uma data e um território |
| Granularidade | espacial: Brasil, regiões, estados, municípios e outros níveis (AMC, mesorregião, microrregião, área metropolitana); temporal: da data da observação: trimestre a década, conforme a série |
| Formato bruto | JSON da API OData v4 do Ipeadata (função `ValoresSerie`), um arquivo por série; um arquivo mistura vários níveis territoriais |
| Estado no lake | convertido |
| Partições | `nivel`, `periodicidade` |
| Chave | `sercodigo`, `valdata`, `nivnome`, `tercodigo` |
| Colunas | 7 |
| Unidades de medida | `valvalor`: varia por série (series.uninome e series.mulnome); `valor`: varia por série (series.uninome e series.mulnome) |
| Dados pessoais | nenhum |
| Eras | nenhuma |
| Revisado em | 2026-11-10 |
| Versão do fetcher | 0.3.2 |

## Origem e coleta

- Mesma coleta de `valores`: um JSON por série da função `ValoresSerie`, nas pastas `regional/`, `social/` e também em `series/` quando a série tem território.
- Arquivos no bruto em 2026-11-10: 166 códigos em `regional/` (16 com mais de uma versão), 2 em `social/` e 90 códigos de `series/` que também estão em `regional/`.
- O conversor decide que a série é regional quando a pasta se chama `regional` ou quando alguma linha tem `NIVNOME` preenchido.

## Conteúdo

- Uma linha por série, data e território. Amostra de 9 séries (5 regionais e 2 sociais, mais 2 de `series/`): 167.746 linhas, 85 datas distintas de 1985-01-01 a 2026-04-01, 13 níveis territoriais, sem chave repetida.
- Níveis na amostra (`nivel`): Brasil, Regioes, Estados, Municipios, Microrregioes, Mesorregioes, Area_metropolitana e AMC_* (1872-00, 20-00, 40-00, 60-00, 70-00, 91-00).
- Periodicidades na amostra: anual 146.381 linhas, decenal 16.776 e trimestral 4.589.
- A cobertura inicial de 1985 vem da amostra e não vale para todas as séries.

## Variáveis

| Coluna no lake | Na fonte | Tipo | Descrição | Unidade / códigos | Período |
|---|---|---|---|---|---|
| `sercodigo` | SERCODIGO | texto | Código da série | — | todo |
| `valdata` | VALDATA | texto | Data do valor, como a API entrega, com hora e fuso | ISO 8601 | todo |
| `valvalor` | VALVALOR | decimal | Valor da série na data e no território | varia por série; ver `series.uninome` e `series.mulnome` | todo |
| `nivnome` | NIVNOME | texto | Nome do nível territorial, como na API | ex.: `Municípios`, `AMC 1872-00` | todo |
| `tercodigo` | TERCODIGO | texto | Código do território dentro do nível | código IBGE ou interno; ver `territorios` | todo |
| `data` | — (gerada) | texto | Data no formato AAAA-MM-DD (10 primeiros caracteres de `valdata`) | AAAA-MM-DD, texto | todo |
| `valor` | — (gerada) | decimal | Cópia de `valvalor` convertida para decimal | igual a `valvalor` | todo |

## No lake

- Dataset `ipeadata/valores_regional`, particionado por `nivel` e `periodicidade`: `nivel=Municipios/periodicidade=anual/<SERCODIGO>.parquet`. Um arquivo da fonte que mistura níveis vira um arquivo por nível.
- `nivel` é `nivnome` sem acento nem espaço (`Regiões` vira `Regioes`, `AMC 1872-00` vira `AMC_1872-00`); sem nível, a linha vai para `nivel=__HIVE_DEFAULT_PARTITION__`.
- `periodicidade` como em `valores`.
- Chave natural: (`sercodigo`, `valdata`, `nivnome`, `tercodigo`), sem repetição na amostra.
- O conversor lê o JSON da série (`ValoresSerie`), renomeia as colunas para minúsculas e acrescenta `data` (os 10 primeiros caracteres de `valdata`, sem deslocamento de fuso) e `valor` (`valvalor` como decimal; o que não converte vira nulo).
- Textos vazios em `nivnome` e `tercodigo` viram nulo.

## Cuidados de uso

- **Mesma série em mais de uma pasta** (mesma causa de `valores`): 90 códigos aparecem em `regional/` e `series/`, e 2 em `series/` e `social/` (`PNADCT_PERDESUF` e `PNADCT_TXDSCUPUF`). O conversor mantém só a cópia de carimbo mais recente de qualquer pasta. Antes da correção (até a 0.3.2) a última pasta em ordem alfabética substituía as outras mesmo sendo mais antiga: em `ADMISNC`, a cópia de `series/` (448.562 linhas, de 2026-11-04) vencia a de `regional/` (454.175, de 2026-11-05). Se o lake foi gerado por versão anterior, reconverta (veja o `CHANGELOG.md`).
- **Junte por nível e código.** `tercodigo` sozinho repete entre níveis; use `nivnome` e `tercodigo` com `territorios`.
- **Nome do nível.** `nivel` (partição) e `nivnome` (coluna) diferem: `Municipios` e `Municípios`.
- **Escala e unidade por série.** Consulte `series.uninome` e `series.mulnome`.
- **Valores muito grandes.** O máximo da amostra é 47,2 bilhões (série de despesa ou crédito); confira a escala antes de agregar níveis.
- **Não some níveis.** Brasil, regiões, estados e municípios convivem no mesmo dataset; somar todos conta o mesmo valor várias vezes.
- **Séries sociais.** `base=social` nunca é usada: as séries sociais estão aqui, não em `valores`.

## Exemplos

Valor de uma série para os estados (nível `Estados`), sem somar com outros níveis:

```python
import duckdb

duckdb.sql("""
    SELECT v.data, t.ternome AS estado, v.valor
    FROM read_parquet('lake/ipeadata/valores_regional/nivel=Estados/**/*.parquet', hive_partitioning = true) v
    JOIN read_parquet('lake/ipeadata/territorios/*.parquet') t
      ON t.nivnome = 'Estados' AND t.tercodigo = v.tercodigo
    WHERE v.sercodigo = 'DFCOME'
    ORDER BY v.data, estado
    LIMIT 20
""").show()
```

## Referências

- API do Ipeadata (entidades Valores e Territórios): http://www.ipeadata.gov.br/api/
- Direitos de uso: http://www.ipeadata.gov.br/iframe_direitouso.aspx
