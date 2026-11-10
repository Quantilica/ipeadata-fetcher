---
dataset:
  id: "territorios"
  fonte: "ipeadata"
  titulo: "Territórios do Ipeadata"
  resumo: "Territórios (Brasil, regiões, estados, municípios, AMCs e outros) a que se referem os valores das séries regionais e sociais."
  orgao: "Instituto de Pesquisa Econômica Aplicada (Ipea)"
  pagina_oficial: "http://www.ipeadata.gov.br/api/"
  licenca: "Termo de Direitos de Uso do Ipeadata: o conteúdo é informação pública que pode ser livremente distribuída e copiada, com obrigação de citar a fonte Ipeadata; sem garantia de exatidão; http://www.ipeadata.gov.br/iframe_direitouso.aspx"
  periodicidade: "atualizada pelo Ipea quando a lista muda; um retrato por coleta"
  cobertura: {inicio: "2026-11", fim: "2026-11"}
  unidade: "um território dentro de um nível territorial"
  granularidade: {espacial: "Brasil, regiões, estados, mesorregiões, microrregiões, municípios, AMCs e outros níveis", temporal: "não se aplica"}
  formato_bruto: "JSON da API OData v4 do Ipeadata (`{\"value\": [...]}`), UTF-8, nomes de campo em maiúsculas"
  lake: {estado: convertido, particoes: [], chave: [nivnome, tercodigo], colunas: 7}
  unidades_de_medida:
    terarea: "km²"
  dados_pessoais: "nenhum"
  eras: []
  revisado_em: "2026-11-10"
  versao_fetcher: "0.3.2"
---

# Territórios do Ipeadata

## Resumo

Os territórios dão nome, código e área aos lugares dos valores regionais e sociais. Um território é identificado pelo par nível e código (`nivnome`, `tercodigo`); só o código não basta.

## Ficha técnica

<!-- gerado:ficha -->

| Campo | Valor |
|---|---|
| Dataset | `ipeadata/territorios` |
| Órgão | Instituto de Pesquisa Econômica Aplicada (Ipea) |
| Página oficial | http://www.ipeadata.gov.br/api/ |
| Licença | Termo de Direitos de Uso do Ipeadata: o conteúdo é informação pública que pode ser livremente distribuída e copiada, com obrigação de citar a fonte Ipeadata; sem garantia de exatidão; http://www.ipeadata.gov.br/iframe_direitouso.aspx |
| Periodicidade | atualizada pelo Ipea quando a lista muda; um retrato por coleta |
| Cobertura | 2026-11 a 2026-11 |
| Unidade (uma linha) | um território dentro de um nível territorial |
| Granularidade | espacial: Brasil, regiões, estados, mesorregiões, microrregiões, municípios, AMCs e outros níveis; temporal: não se aplica |
| Formato bruto | JSON da API OData v4 do Ipeadata (`{"value": [...]}`), UTF-8, nomes de campo em maiúsculas |
| Estado no lake | convertido |
| Partições | — |
| Chave | `nivnome`, `tercodigo` |
| Colunas | 7 |
| Unidades de medida | `terarea`: km² |
| Dados pessoais | nenhum |
| Eras | nenhuma |
| Revisado em | 2026-11-10 |
| Versão do fetcher | 0.3.2 |

## Origem e coleta

- O fetcher chama a API OData v4 do Ipeadata (`http://www.ipeadata.gov.br/api/odata4/`) e grava a resposta como JSON na pasta `dimensoes/`, com o nome `territorios@20261105.json`. O carimbo é fixo e não é a data da coleta: os endpoints não informam versão, e o carimbo fixo faz o arquivo ser substituído no mesmo lugar quando a dimensão muda.
- O conversor lê a lista `value` do JSON e grava um único Parquet.
- Entidade da API: `Territorios`. O arquivo no Drive tinha 3,3 MB em 2026-11-10.

## Conteúdo

- Uma linha por território. Amostra de 2026-11-10: 19.668 linhas em 16 níveis (`nivnome`): Municípios 5.597, AMC 91-00 4.267, AMC 70-00 3.659, AMC 60-00 2.407, AMC 40-00 1.275, AMC 20-00 953, Microrregiões 558, AMC 1872-00 432, Países 231, Mesorregiões 137, Regiões Metropolitanas 107, Estados 27, Área metropolitana 11, Regiões 5, Brasil 1 e um registro com nível vazio (`(não definido)`).
- As AMCs (áreas mínimas comparáveis) são recortes territoriais comparáveis no tempo, conforme o dicionário de conceitos do Ipeadata; `nivamc` marca os níveis desse tipo.

## Variáveis

| Coluna no lake | Na fonte | Tipo | Descrição | Unidade / códigos | Período |
|---|---|---|---|---|---|
| `nivnome` | NIVNOME | texto | Nome do nível territorial | Brasil, Regiões, Estados, Mesorregiões, Microrregiões, Municípios, Regiões Metropolitanas, Área metropolitana, Países, AMC 20-00, AMC 40-00, AMC 60-00, AMC 70-00, AMC 91-00, AMC 1872-00; vazio em um registro | todo |
| `tercodigo` | TERCODIGO | texto | Código do território: código do IBGE para Brasil, Região, Estado, Mesorregião, Microrregião e Município; para os demais níveis é o valor de UFMUNDV, coluna de uso interno do Ipeadata | texto; `0` para o Brasil | todo |
| `ternome` | TERNOME | texto | Nome do território | — | todo |
| `ternomepadrao` | TERNOMEPADRAO | texto | Nome padrão: todo em maiúsculas e sem acentos ou ç (na amostra algumas linhas de países mantêm acento) | — | todo |
| `tercapital` | TERCAPITAL | booleano | Indica se o território é capital; vazio em 5.385 linhas | — | todo |
| `terarea` | TERAREA | decimal | Área do território; vazia em 345 linhas | km² | todo |
| `nivamc` | NIVAMC | booleano | Indica se o nível é do tipo AMC | — | todo |

## No lake

- Dataset `ipeadata/territorios`, sem partição; um Parquet `territorios.parquet`.
- Chave: (`nivnome`, `tercodigo`). Na amostra o nível vazio aparece em uma linha com `tercodigo` vazio.
- `tercodigo` é texto (pode ter zeros à esquerda); `tercapital` e `nivamc` são booleanos; `terarea` é decimal.
- Nulos na amostra: `tercapital` 5.385, `terarea` 345, `nivamc` 1.

## Cuidados de uso

- **O código sozinho não identifica.** `tercodigo` repete entre níveis (quando `nivamc` é falso não repete, segundo a API; quando é verdadeiro pode repetir). Junte sempre por `nivnome` e `tercodigo`.
- **Nível dos valores.** Em `valores_regional` o nível vem em `nivnome` com os nomes originais (`Municípios`); a partição `nivel` usa a forma sem acento e sem espaço (`Municipios`). Para juntar com esta tabela use a coluna `nivnome`.
- **Código do IBGE só em alguns níveis.** Para AMCs e outros níveis `tercodigo` é um código interno do Ipeadata.
- **Retrato, sem histórico.** A dimensão é a lista vigente na data da coleta (2026-11-05); mudanças anteriores não ficam registradas.
- **Nomes de coluna.** O conversor passa o nome do campo da API para minúsculas, sem acento (`SERNOME` vira `sernome`).

## Exemplos

Municípios de uma UF com a área:

```python
import duckdb

duckdb.sql("""
    SELECT tercodigo, ternome, terarea
    FROM read_parquet('lake/ipeadata/territorios/*.parquet')
    WHERE nivnome = 'Municípios' AND tercodigo LIKE '35%'
    ORDER BY terarea DESC LIMIT 10
""").show()
```

## Referências

- API do Ipeadata (entidade Território): http://www.ipeadata.gov.br/api/
