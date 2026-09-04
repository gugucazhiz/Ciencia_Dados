# Notícias da EAJ/UFRN

Coleta, com **Scrapy + Playwright**, as notícias do portal da UFRN que
mencionam a **EAJ** (Escola Agrícola de Jundiaí) e apresenta, em um
dashboard **Streamlit**, a quantidade de notícias por ano.

## Objetivo

1. Um spider Scrapy acessa `https://www.ufrn.br/imprensa/noticias/filtros?keyword=EAJ`,
   amplia o filtro visual para os dez anos-calendário mais recentes, percorre
   a paginação e extrai **URL**, **título** e **ano de publicação** dos blocos
   renderizados, salvando tudo em `data/noticias_eaj.csv` (sem duplicatas).
2. Um app Streamlit lê esse CSV e mostra um gráfico de barras com a
   quantidade de notícias por ano, além de métricas e uma tabela navegável.

## Por que Playwright?

A página de busca é uma SPA: o HTML devolvido pelo servidor traz os
contêineres `#qtd-resultados`, `#noticias-list` e `#noticias-paginacao`
**vazios** — quem preenche isso é o JS oficial da página
(`noticias_filtros.js`), executado no navegador. O mesmo vale para cada
notícia individual: `h1.sec-title` e `span#date_create` existem no HTML
bruto, mas vazios, preenchidos por `noticia.js`. Não há sitemap, RSS ou
listagem HTML estática alternativa disponível (verificado em 03/09/2026).

Como o Scrapy sozinho não executa JavaScript, o spider usa
[`scrapy-playwright`](https://github.com/scrapedin/scrapy-playwright) para
que as requisições sejam feitas por um **Chromium headless real**: o mesmo
JS oficial do portal roda normalmente e o Scrapy recebe o DOM já
renderizado. O código do projeto não chama a API da UFRN diretamente — é o
próprio front-end do site que faz isso, como faria para qualquer visitante.

A paginação (`#noticias-paginacao`) também é via JS (clique que atualiza o
conteúdo sem navegar para uma nova URL), então o spider mantém uma página do
navegador aberta (`playwright_include_page=True`) e faz, em loop: extrai os
links atuais → clica no botão de "próxima" → espera a lista mudar → repete,
até não haver mais próxima página ou o clique não mudar nada.

### Recorte dos últimos dez anos

O serviço JavaScript do portal possuía um corte local fixo que escondia quase
todo o histórico, embora o contador e as 44 páginas continuassem indicando
440 resultados. Antes de a página carregar, o Playwright intercepta somente
o arquivo `noticias_service.js` e substitui essa data local pelo primeiro dia
do ano inicial do recorte. A página continua realizando suas próprias
requisições e construindo o DOM normalmente; o scraper não chama nem analisa
diretamente a resposta da API.

O intervalo é calculado a cada execução. Em 2026, por exemplo, são incluídos
os anos-calendário de **2017 a 2026**, inclusive. O spider também valida esse
intervalo antes de exportar cada item.

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium    # baixa o navegador headless (obrigatório)
```

Em Linux, se faltarem bibliotecas do sistema para o Chromium rodar, use:

```bash
playwright install --with-deps chromium
```

## Antes de rodar o crawl completo: diagnóstico rápido

```bash
python scripts/diagnostico_playwright.py
```

Esse script abre a página real, espera o JS renderizar e imprime quantos
links de notícia foram encontrados (e testa a extração de data na primeira
notícia).
É bem mais rápido que rodar `scrapy crawl` inteiro e ajuda a confirmar que
os seletores (`#noticias-list .noticia h2 a.blue-link`, `#qtd-resultados`,
`h1.sec-title`, `#date_create`, botão de "próxima página") ainda batem com o site real —
esses seletores foram definidos por inspeção manual do DOM renderizado e
podem mudar se a UFRN atualizar o front-end.

Se o script travar em "Esperando o JavaScript popular #noticias-list",
abra `scripts/diagnostico_playwright.py`, troque `headless=True` por
`headless=False` e rode de novo para observar visualmente o que a página
está fazendo.

## Executar o scraper

A partir da raiz do projeto (onde está `scrapy.cfg`):

```bash
scrapy crawl ufrn_eaj
```

Isso gera/atualiza `data/noticias_eaj.csv` com colunas `ano,url,titulo`
(cada execução sobrescreve o arquivo com um snapshot novo). Acompanhe o log
no terminal — o spider registra, por página, quantos links achou e o texto
de `#qtd-resultados`, além de avisos sobre notícias sem ano identificado.

Rodar com Chromium real é mais lento e pesado que HTML puro; o
`DOWNLOAD_DELAY`, o `AUTOTHROTTLE` e `PLAYWRIGHT_MAX_PAGES_PER_CONTEXT` em
`scraper/settings.py` já estão ajustados para não sobrecarregar o servidor
nem a sua máquina. `PLAYWRIGHT_ABORT_REQUEST` bloqueia imagens/CSS/fontes
para acelerar cada navegação.

O cache HTTP do Scrapy fica desativado de propósito. Respostas Playwright
incluem uma página de navegador viva durante a paginação; reutilizar um HTML
antigo do cache faria o callback receber uma resposta sem essa página.

### Resultado validado

Em teste real realizado em 3 de setembro de 2026, o spider percorreu as 44
páginas e exportou os 440 resultados indicados pelo portal. O CSV resultante
cobriu todos os anos de 2017 a 2026, sem URLs duplicadas e sem campos de ano,
título ou URL vazios. A quantidade poderá mudar em execuções futuras porque
o portal recebe novas publicações.

## Executar o Streamlit

```bash
streamlit run streamlit_app.py
```

O dashboard lê `data/noticias_eaj.csv`. Se o arquivo não existir ou estiver
vazio, ele mostra um aviso em vez de inventar dados — rode o scraper antes.

## Como validar sem depender do site no ar

```bash
pytest tests/ -v
```

- `tests/test_utils.py` — extração de ano (datas ISO, numéricas, por
  extenso, priorização de contexto "publicado em") e normalização de URL.
- `tests/test_spider_parsing.py` — extração/deduplicação de links e
  extração de ano/título da listagem renderizada, usando HTML sintético
  (`tests/fixtures/`) que simula o DOM **já renderizado**.

Esses testes não usam um navegador de verdade — cobrem a lógica de parsing
pura. A orquestração via Playwright (clicar em "próxima", esperar o JS)
só é verificável com um Chromium real e internet, via
`scripts/diagnostico_playwright.py` ou `scrapy crawl ufrn_eaj`.

## Estrutura

```text
.
├── scrapy.cfg
├── requirements.txt
├── README.md
├── data/
│   └── noticias_eaj.csv       # gerado por `scrapy crawl ufrn_eaj` (não versionado)
├── scraper/
│   ├── items.py                # NoticiaItem: url, ano, titulo, origem
│   ├── settings.py              # user-agent, robots.txt, delay, playwright, pipelines
│   ├── pipelines.py             # normalização/dedup de URL + validação de ano
│   ├── utils.py                 # funções puras: extract_year_*, normalize_url
│   └── spiders/
│       └── ufrn_eaj.py          # spider principal (Playwright: busca, paginação, notícia)
├── scripts/
│   └── diagnostico_playwright.py  # checagem rápida dos seletores, sem Scrapy
├── streamlit_app.py             # dashboard: gráfico por ano + métricas + tabela
└── tests/                       # testes offline (pytest), com fixtures HTML
```

## Boas práticas de coleta aplicadas

- `ROBOTSTXT_OBEY = True`
- `USER_AGENT` identificando claramente o bot e o propósito acadêmico
- `DOWNLOAD_DELAY` + `AUTOTHROTTLE_ENABLED`, concorrência baixa por domínio
- `PLAYWRIGHT_MAX_PAGES_PER_CONTEXT` limitando páginas simultâneas do navegador
- `PLAYWRIGHT_ABORT_REQUEST` bloqueando recursos irrelevantes (imagens/CSS/fontes)
- Retentativa automática (`RETRY_TIMES`) em erros HTTP transitórios
- Tratamento de erro de requisição via `errback` no spider

## Validação contra o portal real

O fluxo completo foi validado em 3 de setembro de 2026 com Scrapy 2.18,
scrapy-playwright 0.0.48, Playwright 1.62 e Chromium headless. O teste
confirmou navegação, renderização da busca, avanço pelas 44 páginas e
exportação de 440 registros com ano, URL e título para CSV.

O spider usa `async def start()`, exigido pelo Scrapy 2.18. Implementações
antigas baseadas apenas em `start_requests()` encerram imediatamente nessa
versão, sem registrar `downloader/request_count` no log.
