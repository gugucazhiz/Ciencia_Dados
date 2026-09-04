"""Configurações do projeto Scrapy — coleta de notícias da EAJ/UFRN.

Os valores aqui priorizam boas práticas de scraping: identificação clara do
bot, respeito ao robots.txt, delay entre requisições e autothrottle para não
sobrecarregar o servidor da UFRN.
"""

BOT_NAME = "eaj_noticias"

SPIDER_MODULES = ["scraper.spiders"]
NEWSPIDER_MODULE = "scraper.spiders"

# Identificação clara do bot, incluindo um contato, como recomendam as boas
# práticas de scraping (facilita que o administrador do site nos identifique
# e entre em contato caso necessário).
USER_AGENT = (
    "eaj-noticias-bot/1.0 "
    "(+https://github.com/; projeto academico de coleta de noticias EAJ/UFRN)"
)

# Respeita as regras de robots.txt do site.
ROBOTSTXT_OBEY = True

# Não sobrecarrega o servidor: 1 requisição concorrente por domínio e um
# intervalo mínimo entre requisições, com jitter aleatório (padrão do Scrapy).
CONCURRENT_REQUESTS = 4
CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 1.5
RANDOMIZE_DOWNLOAD_DELAY = True

# Ajusta automaticamente a velocidade de acordo com a resposta do servidor.
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1.5
AUTOTHROTTLE_MAX_DELAY = 20
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

# Tenta novamente em caso de erro transitório antes de desistir da página.
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 522, 524, 408, 429]

DOWNLOAD_TIMEOUT = 60

# --- Playwright: a página de busca e as páginas de notícia são renderizadas
# via JavaScript (ver README, seção "Por que Playwright?"). O Scrapy sozinho
# não executa esse JS, então delegamos o download das requisições marcadas
# com meta={"playwright": True} a um navegador Chromium headless controlado
# pelo scrapy-playwright. Requisições sem essa meta continuam usando o
# downloader padrão do Scrapy normalmente.
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {"headless": True}
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30_000  # ms
# Evita subir dezenas de páginas/contextos simultâneos de um navegador real —
# mantém a coleta leve e respeitosa com o servidor da UFRN.
PLAYWRIGHT_MAX_PAGES_PER_CONTEXT = 2

# Bloqueia o carregamento de recursos que não afetam o conteúdo que
# extraímos (imagens, fontes, CSS, mídia), acelerando bastante cada
# navegação no Chromium headless.
PLAYWRIGHT_ABORT_REQUEST = lambda req: req.resource_type in {
    "image", "media", "font", "stylesheet",
}

ITEM_PIPELINES = {
    "scraper.pipelines.NormalizacaoEDedupPipeline": 100,
    "scraper.pipelines.ValidacaoAnoPipeline": 200,
}

# Exporta automaticamente os itens coletados para CSV, na ordem de colunas
# exigida pelo projeto (ano,url). O arquivo é sobrescrito a cada execução do
# spider — isso é intencional: cada `scrapy crawl` gera um snapshot fresco.
FEEDS = {
    "data/noticias_eaj.csv": {
        "format": "csv",
        "encoding": "utf8",
        "fields": ["ano", "url", "titulo"],
        "overwrite": True,
    },
}

LOG_LEVEL = "INFO"

# O cache HTTP do Scrapy não deve armazenar respostas renderizadas pelo
# Playwright: uma resposta antiga pode ser devolvida sem o objeto Page vivo
# necessário à paginação. O Chromium ainda mantém seu cache normal durante
# cada execução.
HTTPCACHE_ENABLED = False

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
