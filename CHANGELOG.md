# Changelog

Todas as alterações notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Adicionado
- Séries inativas (`SERSTATUS != A`, ~2.300): decisão de **não excluir, marcar**. Cada entrada do catálogo (`list`, `sync`, `check`) ganha o atributo `ativa` (bool, `SERSTATUS == "A"`; ausente conta como ativa), e a dimensão `series` do lake ganha a coluna booleana `ativa` (o `serstatus` original continua; arquivo de metadados sem `SERSTATUS` gera `ativa = true`). O `sync` padrão continua baixando tudo; `sync`, `check` e `backfill` aceitam `--somente-ativas` para filtrar as inativas. As tabelas `valores` e `valores_regional` não mudam de esquema (junte com `series` por `sercodigo`). `catalog.list_datasets()`, `list_all_series()` e `list_series_by_base()` ganham o parâmetro `somente_ativas` (padrão `False`).

- `backfill --rebuild-state`: reconstrói o `series/_seratualizacao.json` sem rede de dados (só busca os metadados uma vez). Para cada série, calcula o caminho canônico (`<grupo>/<SERCODIGO>@<SERATUALIZACAO>.json`, o mesmo `path_builder` do `sync`) e, se o arquivo ou o sidecar `.manifest.json` existir, grava `SERCODIGO -> SERATUALIZACAO`. Não depende do banco de ingest.
- `backfill` segura um lock exclusivo (`fcntl.flock` em `series/_seratualizacao.json.lock`) do começo ao fim: uma segunda carga na mesma pasta aborta com mensagem clara e código 2.

### Corrigido
- `backfill`: o estado `_seratualizacao.json` ficava incompleto quando um checkpoint falhava. Na carga de 04/11, o disco de dados sumiu por alguns minutos (BTRFS `emergency shutdown`, `EIO`); a gravação do checkpoint levantou `OSError` dentro do laço, e o pool ainda baixou as ~2.900 séries já enfileiradas sem gravar o estado de novo. Resultado: 950 séries no estado em vez de ~4.100, e o resumo final nunca saiu. Agora a falha de um checkpoint vira aviso e a gravação é tentada de novo no checkpoint seguinte. Uma interrupção cancela o que falta baixar e grava o estado parcial. A gravação final continua obrigatória.
- `save_state` une o estado em memória ao que está em disco, por código, e no conflito vence a `SERATUALIZACAO` mais recente. A troca é atômica, sob um lock curto (`.save.lock`), com arquivo temporário exclusivo de cada gravador. Dois gravadores simultâneos não perdem as chaves um do outro.
- Sem o extra `analysis`, o comando `convert` termina com código 1 e a instrução de instalação (`quantilica install ipeadata --extra analysis`), sem traceback.

### Alterado
- O nome-base dos arquivos brutos vem de `file_key` do `quantilica-core`, com resultado idêntico no lake.
- O comando `backfill` escreve pelo console do SDK, sem `print()`.

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

