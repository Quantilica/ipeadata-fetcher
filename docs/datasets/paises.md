---
dataset:
  id: "paises"
  fonte: "ipeadata"
  titulo: "Países e regiões do Ipeadata"
  resumo: "Países e regiões (como Mundial) a que se associam as séries macroeconômicas do Ipeadata."
  orgao: "Instituto de Pesquisa Econômica Aplicada (Ipea)"
  pagina_oficial: "http://www.ipeadata.gov.br/api/"
  licenca: "Termo de Direitos de Uso do Ipeadata: o conteúdo é informação pública que pode ser livremente distribuída e copiada, com obrigação de citar a fonte Ipeadata; sem garantia de exatidão; http://www.ipeadata.gov.br/iframe_direitouso.aspx"
  periodicidade: "atualizada pelo Ipea quando a lista muda; um retrato por coleta"
  cobertura: {inicio: "2026-11", fim: "2026-11"}
  unidade: "um país ou região"
  granularidade: {espacial: "país", temporal: "não se aplica"}
  formato_bruto: "JSON da API OData v4 do Ipeadata (`{\"value\": [...]}`), UTF-8, nomes de campo em maiúsculas"
  lake: {estado: convertido, particoes: [], chave: [paicodigo], colunas: 2}
  dados_pessoais: "nenhum"
  eras: []
  revisado_em: "2026-11-10"
  versao_fetcher: "0.3.2"
---

# Países e regiões do Ipeadata

## Resumo

Lista de países ou regiões associados às séries macroeconômicas (`series.paicodigo`). Hoje são três: Brasil, Estados Unidos e Mundial.

## Ficha técnica

<!-- gerado:ficha -->

| Campo | Valor |
|---|---|
| Dataset | `ipeadata/paises` |
| Órgão | Instituto de Pesquisa Econômica Aplicada (Ipea) |
| Página oficial | http://www.ipeadata.gov.br/api/ |
| Licença | Termo de Direitos de Uso do Ipeadata: o conteúdo é informação pública que pode ser livremente distribuída e copiada, com obrigação de citar a fonte Ipeadata; sem garantia de exatidão; http://www.ipeadata.gov.br/iframe_direitouso.aspx |
| Periodicidade | atualizada pelo Ipea quando a lista muda; um retrato por coleta |
| Cobertura | 2026-11 a 2026-11 |
| Unidade (uma linha) | um país ou região |
| Granularidade | espacial: país; temporal: não se aplica |
| Formato bruto | JSON da API OData v4 do Ipeadata (`{"value": [...]}`), UTF-8, nomes de campo em maiúsculas |
| Estado no lake | convertido |
| Partições | — |
| Chave | `paicodigo` |
| Colunas | 2 |
| Unidades de medida | — |
| Dados pessoais | nenhum |
| Eras | nenhuma |
| Revisado em | 2026-11-10 |
| Versão do fetcher | 0.3.2 |

## Origem e coleta

- O fetcher chama a API OData v4 do Ipeadata (`http://www.ipeadata.gov.br/api/odata4/`) e grava a resposta como JSON na pasta `dimensoes/`, com o nome `paises@20261105.json`. O carimbo é fixo e não é a data da coleta: os endpoints não informam versão, e o carimbo fixo faz o arquivo ser substituído no mesmo lugar quando a dimensão muda.
- O conversor lê a lista `value` do JSON e grava um único Parquet.
- Entidade da API: `Paises`.

## Conteúdo

- Uma linha por país ou região; três na amostra de 2026-11-10: `BRA` (Brasil), `USA` (Estados Unidos) e `WRLD` (Mundial).
- A API documenta que o código tem três caracteres (ISO 3166-1 alfa-3) quando é país e quatro quando é região.

## Variáveis

| Coluna no lake | Na fonte | Tipo | Descrição | Unidade / códigos | Período |
|---|---|---|---|---|---|
| `paicodigo` | PAICODIGO | texto | Código do país ou região | ISO 3166-1 alfa-3 para países; quatro caracteres para regiões | todo |
| `painome` | PAINOME | texto | Nome do país ou região | — | todo |

## No lake

- Dataset `ipeadata/paises`, sem partição; um Parquet `paises.parquet`.
- Chave: `paicodigo`.
- Duas colunas de texto; sem nulos.

## Cuidados de uso

- **Só valem para a base macroeconômica.** Séries regionais e sociais se referem ao Brasil, mesmo com `paicodigo` vazio (documentação da API).
- **Retrato, sem histórico.** A dimensão é a lista vigente na data da coleta (2026-11-05); mudanças anteriores não ficam registradas.
- **Nomes de coluna.** O conversor passa o nome do campo da API para minúsculas, sem acento (`SERNOME` vira `sernome`).

## Exemplos

```python
import duckdb

duckdb.sql("""
    SELECT p.paicodigo, p.painome, count(*) AS series
    FROM read_parquet('lake/ipeadata/series/*.parquet') s
    JOIN read_parquet('lake/ipeadata/paises/*.parquet') p USING (paicodigo)
    GROUP BY ALL ORDER BY series DESC
""").show()
```

## Referências

- API do Ipeadata: http://www.ipeadata.gov.br/api/
