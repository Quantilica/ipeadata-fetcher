---
dataset:
  id: "temas"
  fonte: "ipeadata"
  titulo: "Temas do Ipeadata"
  resumo: "Lista de temas e subtemas que classificam as séries do Ipeadata."
  orgao: "Instituto de Pesquisa Econômica Aplicada (Ipea)"
  pagina_oficial: "http://www.ipeadata.gov.br/api/"
  licenca: "Termo de Direitos de Uso do Ipeadata: o conteúdo é informação pública que pode ser livremente distribuída e copiada, com obrigação de citar a fonte Ipeadata; sem garantia de exatidão; http://www.ipeadata.gov.br/iframe_direitouso.aspx"
  periodicidade: "atualizada pelo Ipea quando os temas mudam; um retrato por coleta"
  cobertura: {inicio: "2026-11", fim: "2026-11"}
  unidade: "um tema ou subtema"
  granularidade: {espacial: "não se aplica", temporal: "não se aplica"}
  formato_bruto: "JSON da API OData v4 do Ipeadata (`{\"value\": [...]}`), UTF-8, nomes de campo em maiúsculas"
  lake: {estado: convertido, particoes: [], chave: [temcodigo], colunas: 3}
  unidades_de_medida:
    temcodigo_pai: "código do tema pai (sem unidade)"
  dados_pessoais: "nenhum"
  eras: []
  revisado_em: "2026-11-10"
  versao_fetcher: "0.3.2"
---

# Temas do Ipeadata

## Resumo

Os temas organizam as séries do Ipeadata em assuntos (por exemplo, Agropecuária) e subtemas. Cada série aponta para um tema por `series.temcodigo`.

## Ficha técnica

<!-- gerado:ficha -->

| Campo | Valor |
|---|---|
| Dataset | `ipeadata/temas` |
| Órgão | Instituto de Pesquisa Econômica Aplicada (Ipea) |
| Página oficial | http://www.ipeadata.gov.br/api/ |
| Licença | Termo de Direitos de Uso do Ipeadata: o conteúdo é informação pública que pode ser livremente distribuída e copiada, com obrigação de citar a fonte Ipeadata; sem garantia de exatidão; http://www.ipeadata.gov.br/iframe_direitouso.aspx |
| Periodicidade | atualizada pelo Ipea quando os temas mudam; um retrato por coleta |
| Cobertura | 2026-11 a 2026-11 |
| Unidade (uma linha) | um tema ou subtema |
| Granularidade | espacial: não se aplica; temporal: não se aplica |
| Formato bruto | JSON da API OData v4 do Ipeadata (`{"value": [...]}`), UTF-8, nomes de campo em maiúsculas |
| Estado no lake | convertido |
| Partições | — |
| Chave | `temcodigo` |
| Colunas | 3 |
| Unidades de medida | `temcodigo_pai`: código do tema pai (sem unidade) |
| Dados pessoais | nenhum |
| Eras | nenhuma |
| Revisado em | 2026-11-10 |
| Versão do fetcher | 0.3.2 |

## Origem e coleta

- O fetcher chama a API OData v4 do Ipeadata (`http://www.ipeadata.gov.br/api/odata4/`) e grava a resposta como JSON na pasta `dimensoes/`, com o nome `temas@20261105.json`. O carimbo é fixo e não é a data da coleta: os endpoints não informam versão, e o carimbo fixo faz o arquivo ser substituído no mesmo lugar quando a dimensão muda.
- O conversor lê a lista `value` do JSON e grava um único Parquet.
- Entidade da API: `Temas`.

## Conteúdo

- Uma linha por tema ou subtema. Amostra de 2026-11-10: 65 registros; 27 sem tema pai (temas) e 38 com tema pai (subtemas), distribuídos entre 8 temas pais.
- A hierarquia tem um só nível: cada subtema pertence a um único tema.

## Variáveis

| Coluna no lake | Na fonte | Tipo | Descrição | Unidade / códigos | Período |
|---|---|---|---|---|---|
| `temcodigo` | TEMCODIGO | inteiro | Código único do tema | — | todo |
| `temcodigo_pai` | TEMCODIGO_PAI | inteiro | Código do tema pai; vazio indica que o registro é um tema, preenchido que é um subtema | — | todo |
| `temnome` | TEMNOME | texto | Nome do tema, em português | até 30 posições | todo |

## No lake

- Dataset `ipeadata/temas`, sem partição; um Parquet `temas.parquet`.
- Chave: `temcodigo`, sem repetição na amostra.
- Os códigos são inteiros; `temcodigo_pai` tem 27 nulos (os temas).

## Cuidados de uso

- **Subtemas cruzam com séries.** O `temcodigo` de uma série pode ser de um subtema; para agrupar por tema, junte `temcodigo_pai`.
- **Retrato, sem histórico.** A dimensão é a lista vigente na data da coleta (2026-11-05); mudanças anteriores não ficam registradas.
- **Nomes de coluna.** O conversor passa o nome do campo da API para minúsculas, sem acento (`SERNOME` vira `sernome`).

## Exemplos

Subtemas com o nome do tema pai:

```python
import duckdb

duckdb.sql("""
    SELECT s.temcodigo, s.temnome AS subtema, p.temnome AS tema
    FROM read_parquet('lake/ipeadata/temas/*.parquet') s
    JOIN read_parquet('lake/ipeadata/temas/*.parquet') p ON s.temcodigo_pai = p.temcodigo
    ORDER BY tema, subtema
""").show()
```

## Referências

- API do Ipeadata: http://www.ipeadata.gov.br/api/
