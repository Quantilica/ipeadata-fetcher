# Changelog

Todas as alterações notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Alterado

- Sem `DATA_DIR`, o diretório de dados deixa de ser `~/data` e passa a ser `$XDG_DATA_HOME/quantilica` (ou `~/.local/share/quantilica`). Quem define `DATA_DIR` não muda de caminho.

## [0.6.1] - 2026-11-19

### Alterado

- **Build do lake sem mudança não lê o bruto.** Com tudo em dia, `convert(datasets=[...])` decide só por `stat`, sidecars `.manifest.json` e rodapés de Parquet do lake: não abre os JSON das séries nem os de metadados, e o sha256 vem do sidecar (`quantilica.analytics.lake.sha256_file`) em vez de reler o arquivo. As séries são conferidas pelos membros dos arquivos agrupados (sha256 e versões do conversor), pela pasta de origem e pela periodicidade registrada; esta vem da dimensão `series` do lake quando ela foi gravada a partir do mesmo arquivo de metadados, senão do JSON. Só a série sem nenhum registro no lake (por exemplo, a de lista vazia) ainda é aberta. Qualquer mudança (série nova ou revisada, sidecar ausente, `force`, membro órfão, visão parcial do bruto) cai no caminho completo de antes, com o mesmo resultado.
- **Conversão interrompida deixa de virar pulo permanente.** Cada grupo de valores passa a declarar, no rodapé de cada membro (`GroupMember.origin_outputs`), todos os grupos que a série ocupa (um por ano, e por nível nas regionais), e o caminho rápido do build sem mudança só pula uma série quando `LakeWriter.origin_complete` confirma que todos existem, além do sha256 e das versões do conversor. Antes, um build que falhava num grupo novo de uma série revisada deixava os outros grupos em dia e o grupo faltante nunca era tentado de novo. Lake gravado antes desta versão não tem a declaração: a primeira execução depois da atualização reconverte os valores (uma vez), e as seguintes voltam a pular. Exige `quantilica-analytics>=0.15.0`.
- Série que sai da pasta `regional` (mesmo bruto, outra pasta) deixa de ser pulada pelo registro de `valores_regional`: o build reconverte e a série vai para o dataset certo. Vale também para a pasta `social`: uma série sem `NIVNOME` que saiu de `regional` para `social` deve ir para `valores` com `base=social`, e o caminho rápido a pulava. Fora de `regional`, uma série registrada em `valores_regional` só é pulada se algum registro tem `nivel` diferente de `__HIVE_DEFAULT_PARTITION__` (prova do `NIVNOME` nos dados, que o mesmo sha256 mantém); sem essa prova segue o caminho completo. O sha256 já calculado por série é repassado a `origin_complete`/`origin_outputs` (`digest=`), sem reler o sidecar.
- Falha de leitura do bruto ao calcular o sha256 (montagem de rede com erro de E/S) no caminho rápido, ou no teste de uma dimensão, não derruba mais o `convert`: o caminho completo roda e reporta o erro da série.
- `CONVERTER_VERSION` ganha nota: mudança de partição, de dataset ou do nome do grupo exige subir a constante, porque o build sem mudança só confere o destino registrado pela pasta do bruto e pelos metadados.
- As dimensões (`series`, `temas`, `territorios`, `paises`) já gravadas pulam a leitura do JSON, mas seguem contadas como convertidas.
- Uma execução só de dimensões não abre mais as séries de valores (antes lia todas e descartava o resultado); por isso `skipped` não conta mais as séries vazias nessa execução.
- CI e infraestrutura alinhados ao template (fetcher-template v0.2.1).

### Corrigido

- `lake`: o ano de `VALDATA` é convertido sem modo estrito. Com versões recentes do `polars` o ramo da conversão era avaliado também nas linhas sem data AAAA-, e a série com uma data inválida falhava com o erro de conversão do `polars` em vez do erro da série ("N linha(s) sem data"); a linha sem data continua sendo erro da série e não cria partição de ano nula.

## [0.6.0] - 2026-11-16
### Alterado
- **Quebra de layout no lake: `valores` e `valores_regional` passam a ser particionados também por ano, com um Parquet por pasta e todas as séries do ano.** A dimensão `series` e as demais não mudam. Antes e depois:
  - `valores`, antes: `base=macro/periodicidade=mensal/PRECOS_IPCAG.parquet` (um Parquet por série, todos os anos juntos); depois: `base=macro/periodicidade=mensal/ano=2024/valores_macro_mensal.parquet` (um por base, periodicidade e ano, com as observações de todas as séries que têm dados naquele ano).
  - `valores_regional`, antes: `nivel=Municipios/periodicidade=anual/ADH_IDHM.parquet`; depois: `nivel=Municipios/periodicidade=anual/ano=2010/valores_regional_Municipios_anual.parquet`.
  - `ano` é o ano da data da observação (`data`, os 10 primeiros caracteres de `valdata`), inteiro. O arquivo tem o mesmo nome em todos os `ano=` (o ano está na pasta).
  - Cada linha ganha a coluna `_origem` (o código do arquivo bruto da série) e o rodapé do Parquet lista as séries do arquivo (`quantilica.members`, com sha256 e linhas de cada uma). Nenhuma coluna existente muda de nome. Um mesmo arquivo bruto aparece como membro em vários arquivos, um por ano que ele cobre (e por nível, nas regionais).
  - A lista de séries de cada arquivo é a das séries vigentes do bruto: uma série revisada que perdeu as linhas de um ano sai do arquivo daquele ano (e o arquivo some se era a única), e uma série que sai do bruto ou muda de periodicidade, de base ou de nível sai dos arquivos antigos. Uma série sem mudança não reescreve nenhum arquivo: só o ano de uma série alterada é reescrito, e só essa série é relida do JSON.
  - `valvalor` passa a ser sempre decimal (`double`); antes uma série só com valores inteiros gravava `Int64`. As demais colunas do JSON são texto. Os valores são os mesmos.
  - Na reconversão os Parquets antigos por série saem sozinhos depois que os arquivos por ano são publicados (só os escritos por este dataset, não agrupados, com o nome da série, e só de série cujos arquivos foram todos escritos ou conferidos); um Parquet antigo de série que já não está no bruto fica no lake e deve ser apagado à mão.
  - `ConvertResult.converted` e `skipped` passam a contar séries do bruto (antes, `converted` contava um arquivo por série e nível, e as séries sem mudança também eram contadas como convertidas); a dimensão `series` continua contando como convertida a cada execução. Erros do agrupamento começam por `Erro ao converter grupo <dataset>_...`.
  - **Séries que não podem ser lidas** (JSON ilegível; versão vigente vazia ou sem `VALDATA`/`VALVALOR` de série que já está no lake; linhas sem data `AAAA-MM-DD`) são erro em `ConvertResult.errors` e falha de leitura **daquela série**: os arquivos do lake que a têm como membro não descartam membros nem são removidos, e os Parquets antigos dela ficam; os demais arquivos seguem com a regra normal (uma série que mudou de periodicidade sai dos arquivos antigos mesmo que o JSON de outra esteja quebrado). Série vazia que nunca teve linhas no lake continua só pulada (`skipped`).
  - **Linha sem data `AAAA-MM-DD`** em `VALDATA` não cria mais `ano=__HIVE_DEFAULT_PARTITION__`: a série inteira é erro, com a contagem de linhas inválidas na mensagem.
  - **Trava contra visão parcial do bruto**: se mais de `max(25, 2%)` das séries que os rodapés do lake conhecem em um dataset não estão no bruto, a execução converte o que pode sem descartar nem remover nada e termina com um erro que explica; `IPEADATA_FETCHER_ALLOW_PRUNE=1` libera o descarte.
  - **Resíduo do layout antigo**: ao fim de `convert`, todo Parquet de `valores` e `valores_regional` fora de uma pasta `ano=` (por exemplo, o de uma série que saiu do bruto) é listado em `errors`, com o caminho; nada é apagado além do que a migração já substitui.
  - **A segunda execução ainda lê todos os JSON** para saber os anos de cada série e montar a lista de membros; o que ela evita é reescrever arquivo e reler/normalizar de novo a série sem mudança (nenhuma fatia é gerada).
- O conversor registra `contract_version` (1) e `converter_version` ("1") em cada série do grupo; mudar a leitura dos valores e subir uma delas reconverte tudo.
- Exige `quantilica-analytics>=0.12.0` no extra `analysis` (`write_group`).
- Documentação dos dados de `valores` e `valores_regional`: partição `ano` e coluna `_origem`.

### Adicionado
- Testes de equivalência do agrupamento: o conteúdo do lake (linhas, colunas e tipos, anos e hash do conteúdo ordenado, por dataset e por base ou nível e periodicidade) é igual ao do conversor de um Parquet por série (`tests/golden/lake_antes_do_agrupamento.json`, gerado antes da mudança; a única diferença é `valvalor` inteiro virar `double`), mais segunda execução sem reescrita nem releitura, série revisada que perde ou ganha um ano, série que sai do bruto ou muda de periodicidade, migração do layout antigo sem linhas duplicadas, JSON ilegível sem perda de dados e sem desligar o descarte dos demais, versão vazia, linha sem data, visão parcial do bruto nos dois lados do limite, `lake_audit` limpo e `profile_from_lake` com período anual.
- Testes: identidade do registro conferida.

### Corrigido
- CI: o pyproject declara o PyPI antes do índice Quantilica (`[[tool.uv.index]]`), e o workflow perde `--index` e `--index-strategy`. Com a estratégia padrão `first-index`, o `uv sync` só consulta o índice para o que não está no PyPI (`quantilica-analytics`) e deixa de receber o 503 intermitente que o GitHub Pages devolve a caminhos inexistentes.

## [0.5.0] - 2026-11-14

### Adicionado
- O fetcher declara os fatos da fonte (`FetcherInfo`: id canônico, órgão, página e cadência) para o registro de fetchers da Quantilica.

### Alterado
- Requer `quantilica-core>=0.19.0` (e `quantilica-cli>=0.17.0` como host).
- `FetcherInfo.licenca` passa a declarar a licença da fonte: Sem licença declarada; dados públicos pela Lei 12.527/2011 (LAI) e Decreto 8.777/2016.

## [0.4.0] - 2026-11-10

### Corrigido
- A conversão de `valores` e `valores_regional` não perde mais dados quando a mesma série existe em mais de uma pasta do bruto (`macro/` e `series/`, `series/` e `regional/`, `series/` e `social/`). As cópias iam para o mesmo destino no lake (`<SERCODIGO>.parquet`) e a última pasta em ordem alfabética sobrescrevia as outras, mesmo sendo a mais antiga; o resultado ainda contava uma conversão por cópia. Agora vale só a cópia de carimbo mais recente, de qualquer pasta, e a conversão conta uma por série.
- Séries sem nenhum valor (lista `value` vazia) e respostas sem `VALDATA`/`VALVALOR` deixam de ser descartadas em silêncio: o conversor registra um aviso no log e as conta em `skipped`.
- O destino de uma série que existe em mais de uma pasta do bruto passa a depender do conjunto de pastas em que ela existe, e não da pasta da cópia que venceu: com `regional/` entre elas (ou com `NIVNOME` nas linhas) vai para `valores_regional`; com `social/`, a base é `social`; senão, `macro`. Assim a série não muda de partição quando a cópia mais nova passa de uma pasta para outra.
- Arquivos internos do fetcher que começam com `_` (como `_seratualizacao.json`, o estado da carga histórica) não são mais lidos como séries nem geram o aviso de série vazia.

**Como reconverter.** Os nomes dos Parquets não mudam, mas o lake gerado pelas versões anteriores pode ter a série na partição errada ou em duas partições (a cópia que perdeu e a que venceu podiam ir para destinos diferentes), o que duplicaria as linhas numa reconversão comum. Para refazer `valores` e `valores_regional`, apague antes as pastas `ipeadata/valores/` e `ipeadata/valores_regional/` do lake e converta de novo esses dois datasets. As dimensões (`series`, `temas`, `territorios`, `paises`) não são afetadas.

### Adicionado
- Documentação dos dados em `docs/`, conforme a norma de documentação dos dados: página da fonte, página e dicionário de todas as variáveis e esquema de referência para cada um dos seis datasets. Um teste a verifica.

## [0.3.2] - 2026-11-06

### Corrigido

- O pacote volta a carregar no Windows: o lock da carga histórica (`backfill`) usava `fcntl`, que só existe em POSIX, e o import falhava ao abrir o plugin. No Windows o lock passa a usar `msvcrt.locking`.

## [0.3.1] - 2026-11-06

### Corrigido

- A conversão para o lake não falha mais em séries que começam com muitos valores vazios antes do primeiro número: o tipo de cada coluna passa a ser deduzido de todas as linhas.

## [0.3.0] - 2026-11-05

### Adicionado
- Séries inativas (`SERSTATUS != A`, ~2.300): decisão de **não excluir, marcar**. Cada entrada do catálogo (`list`, `sync`, `check`) ganha o atributo `ativa` (bool, `SERSTATUS == "A"`; ausente conta como ativa), e a dimensão `series` do lake ganha a coluna booleana `ativa` (o `serstatus` original continua; arquivo de metadados sem `SERSTATUS` gera `ativa = true`). O `sync` padrão continua baixando tudo; `sync`, `check` e `backfill` aceitam `--somente-ativas` para filtrar as inativas. As tabelas `valores` e `valores_regional` não mudam de esquema (junte com `series` por `sercodigo`). `catalog.list_datasets()`, `list_all_series()` e `list_series_by_base()` ganham o parâmetro `somente_ativas` (padrão `False`).

- `backfill --rebuild-state`: reconstrói o `series/_seratualizacao.json` sem rede de dados (só busca os metadados uma vez). Para cada série, calcula o caminho canônico (`<grupo>/<SERCODIGO>@<SERATUALIZACAO>.json`, o mesmo `path_builder` do `sync`) e, se o arquivo ou o sidecar `.manifest.json` existir, grava `SERCODIGO -> SERATUALIZACAO`. Não depende do banco de ingest.
- `backfill` segura um lock exclusivo (`fcntl.flock` em `series/_seratualizacao.json.lock`) do começo ao fim: uma segunda carga na mesma pasta aborta com mensagem clara e código 2.

### Alterado
- Séries inativas (`SERSTATUS != A`) são baixadas só na primeira vez: o `sync` (inclusive `sync --from-plan`) e o `check` pulam a série inativa que já tem alguma versão local (`<grupo>/<SERCODIGO>@*.json` ou o sidecar `.manifest.json`) ou que consta no estado do `backfill`, mesmo que a `SERATUALIZACAO` do catálogo mude (no `check` o motivo é `inativa-baixada`). Série inativa nunca baixada é baixada uma vez; série ativa segue a política de sempre. `sync --force` rebaixa as inativas. O `backfill` não muda: trata inativas como as demais (use `--somente-ativas` para excluí-las).

### Corrigido
- `backfill`: o estado `_seratualizacao.json` ficava incompleto quando um checkpoint falhava. Na carga de 04/11, o disco de dados sumiu por alguns minutos (BTRFS `emergency shutdown`, `EIO`); a gravação do checkpoint levantou `OSError` dentro do laço, e o pool ainda baixou as ~2.900 séries já enfileiradas sem gravar o estado de novo. Resultado: 950 séries no estado em vez de ~4.100, e o resumo final nunca saiu. Agora a falha de um checkpoint vira aviso e a gravação é tentada de novo no checkpoint seguinte. Uma interrupção cancela o que falta baixar e grava o estado parcial. A gravação final continua obrigatória.
- `save_state` une o estado em memória ao que está em disco, por código, e no conflito vence a `SERATUALIZACAO` mais recente. A troca é atômica, sob um lock curto (`.save.lock`), com arquivo temporário exclusivo de cada gravador. Dois gravadores simultâneos não perdem as chaves um do outro.
- As 4 dimensões (`metadados`, `temas`, `territorios`, `paises`) eram rebaixadas todo dia: os endpoints não têm data de versão (`HEAD` 404, sem `Last-Modified`) e o caminho caía na data de hoje. Agora a entrada aceita o campo `fixed_stamp` (`AAAAMMDD`), que `DataRepository.path_for_entry` aplica antes de qualquer data. As dimensões usam `20261105` e passam a ficar em `dimensoes/<id>@20261105.json`. **Trade-off:** quando uma dimensão muda, o arquivo é substituído no mesmo caminho e não ganha uma versão por dia; o ingest guarda cada conteúdo (sha256) como nova versão do mesmo `original_path`, e o plano Postgres só a rebaixa quando a última versão passa da idade máxima (`pg-stale`). A data é a da última versão diária já ingerida, porque uma data mais antiga (por exemplo `19700101`) perderia para `@20261105` no `select_current` do lake e o lake leria a cópia antiga para sempre. As séries continuam versionadas por `SERATUALIZACAO`.

## [0.2.0] - 2026-11-04

### Adicionado
- `backfill` incremental por `SERATUALIZACAO`: o estado (`SERCODIGO -> SERATUALIZACAO` da última carga válida) fica em `series/_seratualizacao.json`; `--resume` (padrão) só rebaixa séries cuja data mudou (série sem data é sempre rebaixada) e `--restart` rebaixa tudo. Antes o `--resume` só pulava arquivo do mesmo dia, então cada rodada rebaixava as ~4.000 séries.
- `backfill` em paralelo: `--workers` (padrão 3, o valor da carga regional de 11 GB) com pool limitado; `IpeadataClient(workers=N)` aplica `HostPolicy` ao host do OData (`max_concurrency=N`, `min_interval` 0,25 s, `deadline` 900 s).
- `backfill`: série vazia (`value: []`), resposta inválida e falha de rede são erros contados no resumo (o arquivo vazio é descartado, a série fica fora do estado e é tentada de novo); o comando sai com código 1 se houver algum. Atenção: séries legitimamente sem valores (há ~2.300 com `SERSTATUS != A`) também contam como erro.

### Alterado
- O nome-base dos arquivos brutos vem de `file_key` do `quantilica-core`, com resultado idêntico no lake.
- O comando `backfill` escreve pelo console do SDK, sem `print()`.

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
- Sem o extra `analysis`, o comando `convert` termina com código 1 e a instrução de instalação (`quantilica install ipeadata --extra analysis`), sem traceback.

## [0.1.0] - 2026-11-01

### Adicionado
- Versão inicial do pacote `ipeadata-fetcher` (`quantilica ipeadata`).
- Suporte a `list`, `check`, `sync` e verificação de frescor via SDK `FetcherApp`.

- Conversor Universal Hive Parquet Lake com `DatasetSpec` em `lake.py`.

