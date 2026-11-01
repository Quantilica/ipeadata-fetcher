# ipeadata-fetcher

[![CI](https://github.com/Quantilica/ipeadata-fetcher/actions/workflows/test.yml/badge.svg)](https://github.com/Quantilica/ipeadata-fetcher/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

Coletor e conversor Lake Hive para dados abertos de **Instituto de Pesquisa Econômica Aplicada (Ipeadata)** (`ipeadata`), parte do ecossistema [Quantilica](https://quantilica.com).

## Instalação

### Via CLI Quantilica (recomendado)

```bash
quantilica install ipeadata
```

Para instalar com suporte à conversão Parquet Lake:

```bash
quantilica install ipeadata --extra analysis
```

### Como biblioteca Python

```bash
uv add ipeadata-fetcher --index https://index.quantilica.com/simple/
```

Com o extra de análise analítica:

```bash
uv add 'ipeadata-fetcher[analysis]' --index https://index.quantilica.com/simple/
```

## Uso via CLI

```bash
# Listar conjuntos disponíveis
quantilica ipeadata list

# Verificar novos arquivos e frescor
quantilica ipeadata check

# Sincronizar arquivos para o diretório local bruto
quantilica ipeadata sync -o /data/ipeadata

# Converter acervo bruto para o Universal Hive Parquet Lake
quantilica ipeadata convert /data/ipeadata /data/lake
```

## Licença

Distribuído sob licença MIT. Consulte [LICENSE](LICENSE) para mais detalhes.
