---
dataset:
  id: "valores"
  fonte: "ipeadata"
  titulo: "Valores das séries macroeconômicas do Ipeadata"
  resumo: "Observações (data e valor) das séries macroeconômicas do Ipeadata, uma linha por série e data."
  orgao: "Instituto de Pesquisa Econômica Aplicada (Ipea)"
  pagina_oficial: "http://www.ipeadata.gov.br/api/"
  licenca: "Termo de Direitos de Uso do Ipeadata: o conteúdo é informação pública que pode ser livremente distribuída e copiada, com obrigação de citar a fonte Ipeadata; sem garantia de exatidão; http://www.ipeadata.gov.br/iframe_direitouso.aspx"
  periodicidade: "varia por série (diária a decenal; ver `series.pernome`); o Ipeadata registra a última carga em `series.seratualizacao`"
  cobertura: {inicio: "1808", fim: "em-curso"}
  unidade: "valor de uma série numérica macroeconômica em uma data"
  granularidade: {espacial: "Brasil (maioria), Estados Unidos e Mundial", temporal: "da data da observação: dia a década, conforme a série"}
  formato_bruto: "JSON da API OData v4 do Ipeadata (função `ValoresSerie`), um arquivo por série"
  lake: {estado: convertido, particoes: [base, periodicidade], chave: [sercodigo, valdata], colunas: 7}
  unidades_de_medida:
    valvalor: "varia por série (series.uninome e series.mulnome)"
    valor: "varia por série (series.uninome e series.mulnome)"
  dados_pessoais: "nenhum"
  eras: []
  revisado_em: "2026-11-10"
  versao_fetcher: "0.3.2"
---

# Valores das séries macroeconômicas do Ipeadata

## Resumo

Os valores das séries macroeconômicas do Ipeadata (câmbio, juros, preços, produção, contas públicas, entre outras) numa tabela só: uma linha por série e data. Cada série tem sua periodicidade, unidade e fonte, descritas em `series`.

## Ficha técnica

<!-- gerado:ficha -->

| Campo | Valor |
|---|---|
| Dataset | `ipeadata/valores` |
| Órgão | Instituto de Pesquisa Econômica Aplicada (Ipea) |
| Página oficial | http://www.ipeadata.gov.br/api/ |
| Licença | Termo de Direitos de Uso do Ipeadata: o conteúdo é informação pública que pode ser livremente distribuída e copiada, com obrigação de citar a fonte Ipeadata; sem garantia de exatidão; http://www.ipeadata.gov.br/iframe_direitouso.aspx |
| Periodicidade | varia por série (diária a decenal; ver `series.pernome`); o Ipeadata registra a última carga em `series.seratualizacao` |
| Cobertura | 1808 a em-curso |
| Unidade (uma linha) | valor de uma série numérica macroeconômica em uma data |
| Granularidade | espacial: Brasil (maioria), Estados Unidos e Mundial; temporal: da data da observação: dia a década, conforme a série |
| Formato bruto | JSON da API OData v4 do Ipeadata (função `ValoresSerie`), um arquivo por série |
| Estado no lake | convertido |
| Partições | `base`, `periodicidade` |
| Chave | `sercodigo`, `valdata` |
| Colunas | 7 |
| Unidades de medida | `valvalor`: varia por série (series.uninome e series.mulnome); `valor`: varia por série (series.uninome e series.mulnome) |
| Dados pessoais | nenhum |
| Eras | nenhuma |
| Revisado em | 2026-11-10 |
| Versão do fetcher | 0.3.2 |

## Origem e coleta

- O fetcher consulta a função `ValoresSerie(SERCODIGO='<código>')` da API OData v4 do Ipeadata e grava uma resposta JSON por série, com o nome `<SERCODIGO>@AAAAMMDD.json`. As séries estão em duas pastas do bruto: `macro/` (220 códigos em 2026-11-10) e `series/` (3.962 códigos).
- A pasta `regional/` e `social/` guardam séries regionais e sociais, que vão para `valores_regional`.
- Cada série pode ter várias versões com carimbos diferentes; o conversor escolhe a mais recente. Se a mesma série existe em mais de uma pasta, vale só a cópia de carimbo mais recente, de qualquer pasta (as outras são ignoradas e registradas no log).
- Arquivos de valores no bruto em 2026-11-10: 3.962 códigos em `series/`, 220 em `macro/` (40 com mais de uma versão), 166 em `regional/` e 2 em `social/`.

## Conteúdo

- Uma linha por série e data. Na amostra de 7 séries macroeconômicas: 15.370 linhas, 14.476 datas distintas de 1808-08-01 a 2026-11-05, nenhuma chave repetida.
- Das 15.370 linhas da amostra, 5.600 (36%) têm valor nulo, a maior parte na taxa diária da Anbima (`ANBIMA366_TJTLN12366`).
- A cobertura de cada série varia: o catálogo não traz a data inicial; ela só se vê nos valores. A menor data observada na amostra (1808) não vale para as demais séries.
- Três arquivos de `macro/` (`IGP_IGPM`, `INPC_INPC`, `PIB_PIB`; 136 bytes) têm a lista `value` vazia e seus códigos não estão no catálogo; o conversor os ignora, registra um aviso no log e os conta como pulados (`skipped`).

## Variáveis

| Coluna no lake | Na fonte | Tipo | Descrição | Unidade / códigos | Período |
|---|---|---|---|---|---|
| `sercodigo` | SERCODIGO | texto | Código da série (junta com `series.sercodigo`) | — | todo |
| `valdata` | VALDATA | texto | Data do valor, como a API entrega, com hora e deslocamento de fuso (ex.: `T00:00:00-03:00`; vê-se também `-02:00` do horário de verão) | ISO 8601 | todo |
| `valvalor` | VALVALOR | decimal | Valor da série na data, como publicado | varia por série; ver `series.uninome` e `series.mulnome` | todo |
| `nivnome` | NIVNOME | texto | Nível territorial; sempre vazio na base macroeconômica | nulo em todas as linhas da amostra | todo |
| `tercodigo` | TERCODIGO | texto | Código do território; sempre vazio na base macroeconômica | nulo em todas as linhas da amostra | todo |
| `data` | — (gerada) | texto | Data do valor no formato AAAA-MM-DD, os 10 primeiros caracteres de `valdata` | AAAA-MM-DD, texto | todo |
| `valor` | — (gerada) | decimal | Cópia de `valvalor` convertida para decimal | igual a `valvalor` | todo |

## No lake

- Dataset `ipeadata/valores`, particionado por `base` e `periodicidade`: `base=macro/periodicidade=mensal/<SERCODIGO>.parquet`, um arquivo por série.
- `base` é `macro`, exceto quando a pasta do bruto se chama `social`; como as séries sociais têm `nivnome` preenchido, elas vão para `valores_regional`, e `base=social` não ocorre na prática.
- `periodicidade` vem do metadado da série (`pernome`) em minúsculas e sem acento: `diaria`, `mensal`, `trimestral`, `anual`, `decenal`, `quinquenal`, `quadrienal`, `irregular`, `nao_se_aplica`. Série sem periodicidade nos metadados vai para `periodicidade=__HIVE_DEFAULT_PARTITION__`.
- Chave natural: (`sercodigo`, `valdata`), sem repetição na amostra.
- O conversor lê o JSON da série (`ValoresSerie`), renomeia as colunas para minúsculas e acrescenta `data` (os 10 primeiros caracteres de `valdata`, sem deslocamento de fuso) e `valor` (`valvalor` como decimal; o que não converte vira nulo).
- Textos vazios em `nivnome` e `tercodigo` viram nulo.
- Séries cuja resposta não tem `VALDATA` e `VALVALOR`, e séries vazias, são ignoradas com um aviso no log e contadas como puladas (`skipped`).

## Cuidados de uso

- **Mesma série em mais de uma pasta.** Em 2026-11-10 havia mais de cem códigos em `macro/` e `series/`, 90 em `series/` e `regional/` e 2 em `series/` e `social/`. Todas as cópias iriam para o mesmo destino (`<SERCODIGO>.parquet`); o conversor mantém só a de carimbo mais recente. Antes da correção (conversor até a 0.3.2) valia a última pasta em ordem alfabética, mesmo sendo a mais antiga: em `ABRAS12_INVNR12`, a cópia de `macro/` (69 linhas) era substituída pela de `series/` (68). Se o lake foi gerado por versão anterior, reconverta (veja o `CHANGELOG.md`).
- **Unidade e escala por série.** O valor vem como publicado; consulte `series.uninome` e `series.mulnome` antes de somar ou comparar.
- **Muitos nulos.** 36% das linhas da amostra têm valor nulo (7 séries); filtre ou trate antes de calcular.
- **`data` descarta a hora.** `data` é o texto da data local; `valdata` mostra o fuso. Não some horas a `data`.
- **Séries diárias nulas.** A taxa Anbima diária da amostra tem 14.022 linhas, boa parte nulas (feriados e fins de semana).
- **Fontes de terceiros.** O Ipeadata republica séries de outras instituições (campo `series.fntnome`); a exatidão é da fonte original, conforme o termo de uso.
- **Séries inativas.** Séries com `series.serstatus = I` já não recebem atualizações.
- **Revisões.** O Ipeadata pode revisar valores passados; o lake guarda a última versão coletada de cada série.

## Exemplos

Média anual da taxa de juros diária da Anbima em uma série, ignorando nulos (a unidade está em `series`):

```python
import duckdb

duckdb.sql("""
    SELECT year(CAST(data AS DATE)) AS ano, avg(valor) AS media
    FROM read_parquet('lake/ipeadata/valores/**/*.parquet', hive_partitioning = true)
    WHERE sercodigo = 'ANBIMA366_TJTLN12366' AND valor IS NOT NULL
    GROUP BY ano ORDER BY ano
""").show()
```

## Referências

- API do Ipeadata (entidades Metadados e Valores): http://www.ipeadata.gov.br/api/
- Direitos de uso: http://www.ipeadata.gov.br/iframe_direitouso.aspx
