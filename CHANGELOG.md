# Changelog

Todas as alterações notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [0.2.0] - 2026-11-04

### Adicionado
- `backfill` incremental por `SERATUALIZACAO`: o estado (`SERCODIGO -> SERATUALIZACAO` da última carga válida) fica em `series/_seratualizacao.json`; `--resume` (padrão) só rebaixa séries cuja data mudou (série sem data é sempre rebaixada) e `--restart` rebaixa tudo. Antes o `--resume` só pulava arquivo do mesmo dia, então cada rodada rebaixava as ~4.000 séries.
- `backfill` em paralelo: `--workers` (padrão 3, o valor da carga regional de 11 GB) com pool limitado; `IpeadataClient(workers=N)` aplica `HostPolicy` ao host do OData (`max_concurrency=N`, `min_interval` 0,25 s, `deadline` 900 s).
- `backfill`: série vazia (`value: []`), resposta inválida e falha de rede são erros contados no resumo (o arquivo vazio é descartado, a série fica fora do estado e é tentada de novo); o comando sai com código 1 se houver algum. Atenção: séries legitimamente sem valores (há ~2.300 com `SERSTATUS != A`) também contam como erro.

### Corrigido
- `sync todas --dry-run` estourava `ValueError: Grupo desconhecido: 'a'` e
  `sync macro_all` dava "Grupo desconhecido": o `FetcherApp` recebia
  `alias -> str` (o SDK faz `list("all")` -> `['a','l','l']`) e os grupos
  dinâmicos (`all`, `macro_all`, `social_all`, `regional_all`) não eram aliases
  válidos. Também `macro_all` vinha vazio (`"macroeconômico" != "macro"`).
- Catálogo: grupo canônico a partir de `BASNOME` (`Macroeconômico` -> `macro`) e
  campos reais do OData (`PERNOME`, `FNTSIGLA`, `UNINOME`) para periodicidade,
  fonte e unidade (os nomes antigos nunca existiram no payload).
- `lake`: `periodicidade` vem do `PERNOME` do metadado da série (antes
  `"mensal"` fixo) e `nivel` do `NIVNOME` de cada linha (antes `"Municipios"`
  fixo; uma série mistura Municípios, AMC, Estados e Brasil e agora gera uma
  partição por nível). Sem metadado/nível o dado vai para
  `__HIVE_DEFAULT_PARTITION__` com aviso. O roteamento regional olha o arquivo
  todo, não só as 5 primeiras linhas. Reconverter o lake para corrigir as
  partições antigas.
- Testes de rede ficam atrás de `@pytest.mark.network` (fora do `pytest -q`);
  `test_list_datasets_by_group` não acessa mais o OData (levava ~60 s).

## [0.1.0] - 2026-11-01

### Adicionado
- Versão inicial do pacote `ipeadata-fetcher` (`quantilica ipeadata`).
- Suporte a `list`, `check`, `sync` e verificação de frescor via SDK `FetcherApp`.

- Conversor Universal Hive Parquet Lake com `DatasetSpec` em `lake.py`.

