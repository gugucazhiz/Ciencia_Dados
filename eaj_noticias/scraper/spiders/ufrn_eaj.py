"""Spider que coleta, no portal de notícias da UFRN, as notícias que mencionam a EAJ.

## Por que Playwright?

A página de busca (`/imprensa/noticias/filtros?keyword=EAJ`) é uma SPA: o
HTML devolvido pelo servidor traz os contêineres `#qtd-resultados`,
`#noticias-list` e `#noticias-paginacao` **vazios**. Quem preenche esses
elementos é o `noticias_filtros.js`, executado no navegador. O mesmo vale
para a página de cada notícia: `h1.sec-title` e `span#date_create` existem
no HTML bruto, mas vazios, e são populados por `noticia.js`.

Como o Scrapy não executa JavaScript, este spider usa o `scrapy-playwright`
para que as requisições sejam feitas por um Chromium headless de verdade —
o mesmo JS oficial da página é executado, e o Scrapy recebe o DOM já
renderizado (título/data preenchidos, lista de notícias populada). Isso NÃO
chama a API da UFRN diretamente pelo nosso código: é o próprio front-end do
portal que faz essa chamada, como faria para qualquer visitante humano.

O JavaScript oficial também aplica uma data de corte local que esconde o
histórico. Antes da navegação, o spider altera somente essa constante no
script carregado pelo navegador para abranger os dez anos-calendário mais
recentes. Ano, título e URL são então lidos dos blocos da própria listagem,
sem interpretar diretamente a resposta da API e sem abrir uma aba por notícia.

## Paginação

A paginação (`#noticias-paginacao`) também é controlada por JS: não é um
link `<a href="...">` para uma nova URL, e sim algo clicável que atualiza o
conteúdo de `#noticias-list` sem navegar. Por isso a paginação é feita
clicando no botão de "próxima página" *dentro da mesma página do navegador*
(usamos `playwright_include_page=True` para manter um objeto `Page` vivo e
orquestrar clique + espera + reextração em loop), em vez do padrão usual de
"seguir um link para uma nova URL".
"""

from __future__ import annotations

from datetime import datetime
import re
from urllib.parse import urljoin

import scrapy
from scrapy.http import TextResponse
from scrapy.selector import Selector
from scrapy_playwright.page import PageMethod

from scraper.items import NoticiaItem
from scraper.utils import extract_year_from_html, extract_year_from_text

START_URL = "https://www.ufrn.br/imprensa/noticias/filtros?keyword=EAJ"
PORTAL_BASE_URL = "https://www.ufrn.br/"
ANO_FINAL = datetime.now().year
ANO_INICIAL = ANO_FINAL - 9
DATA_CORTE_ISO = f"{ANO_INICIAL}-01-01T00:00:00Z"

URL_SCRIPT_NOTICIAS = "**/resources/js/services/noticias_service.js*"
PADRAO_DATA_CORTE_JS = re.compile(
    r"var\s+dataLimite\s*=\s*new Date\(['\"][^'\"]+['\"]\);"
)

# Seletores confirmados por inspeção real do DOM renderizado (ver docstring).
SELETOR_LISTA_NOTICIAS = "#noticias-list"
SELETOR_LINKS_NOTICIA = "#noticias-list .noticia h2 a.blue-link::attr(href)"
# O Playwright usa CSS do navegador e não entende o pseudo-elemento
# ``::attr(href)`` do Parsel/Scrapy.
SELETOR_LINKS_NOTICIA_DOM = "#noticias-list .noticia h2 a.blue-link[href]"
SELETOR_QTD_RESULTADOS = "#qtd-resultados"
SELETOR_PAGINACAO = "#noticias-paginacao"

# Botão/link de "próxima página" dentro do bloco de paginação. Mantém uma
# lista de candidatos porque não confirmamos a marcação exata do botão —
# o spider tenta cada um, em ordem, e loga qual funcionou.
SELETORES_BOTAO_PROXIMA = [
    f"{SELETOR_PAGINACAO} a[title='Próxima página']",
    f"{SELETOR_PAGINACAO} a[rel='next']",
    f"{SELETOR_PAGINACAO} a.next",
    f"{SELETOR_PAGINACAO} li.next a",
    f"{SELETOR_PAGINACAO} a:has-text('Próxima')",
    f"{SELETOR_PAGINACAO} a:has-text('próxima')",
    f"{SELETOR_PAGINACAO} button:has-text('Próxima')",
]

# Página de notícia individual — título e data são preenchidos via JS.
SELETOR_TITULO = "h1.sec-title"
SELETOR_DATA = "#date_create"

MAX_PAGINAS = 200
TIMEOUT_ESPERA_MS = 45_000


def extrair_links_de_selector(sel: Selector) -> list[str]:
    """Função pura (testável sem Playwright): extrai e deduplica os hrefs de
    notícia a partir de um Selector já contendo o HTML renderizado."""
    hrefs = sel.css(SELETOR_LINKS_NOTICIA).getall()
    vistos: set[str] = set()
    unicos: list[str] = []
    for href in hrefs:
        href = (href or "").strip()
        if href and href not in vistos:
            vistos.add(href)
            unicos.append(href)
    return unicos


def extrair_noticias_de_selector(sel: Selector) -> list[dict]:
    """Extrai ano, título e href dos blocos já renderizados pelo portal."""
    noticias: list[dict] = []
    vistos: set[str] = set()

    for bloco in sel.css(f"{SELETOR_LISTA_NOTICIAS} .noticias-block"):
        data_texto = " ".join(bloco.css(".block-title h1::text").getall()).strip()
        ano = extract_year_from_text(data_texto)

        for link in bloco.css(".noticia h2 a.blue-link"):
            href = (link.attrib.get("href") or "").strip()
            if not href or href in vistos:
                continue

            titulo = " ".join(" ".join(link.css("::text").getall()).split())
            vistos.add(href)
            noticias.append({"href": href, "titulo": titulo, "ano": ano})

    return noticias


def resolver_url_noticia(href: str) -> str:
    """Resolve um href como o navegador, respeitando o ``<base href="/">``."""
    return urljoin(PORTAL_BASE_URL, href)


async def configurar_pagina_busca(page, _request) -> None:
    """Amplia para dez anos o corte aplicado pelo JavaScript oficial.

    A página continua fazendo sua navegação e suas requisições normalmente.
    Alteramos somente a constante local que, no front-end, descarta notícias
    antigas antes de montar o DOM.
    """

    async def reescrever_script(route) -> None:
        response = await route.fetch()
        script_original = await response.text()
        script_alterado, substituicoes = PADRAO_DATA_CORTE_JS.subn(
            f"var dataLimite = new Date('{DATA_CORTE_ISO}');",
            script_original,
        )
        if not substituicoes:
            raise RuntimeError(
                "Não foi possível localizar a data de corte em "
                "noticias_service.js; o portal pode ter mudado."
            )
        await route.fulfill(response=response, body=script_alterado)

    await page.route(URL_SCRIPT_NOTICIAS, reescrever_script)


class UfrnEajSpider(scrapy.Spider):
    name = "ufrn_eaj"
    allowed_domains = ["ufrn.br"]

    async def start(self):
        """Gera a requisição inicial usando a API assíncrona do Scrapy 2.13+.

        O Scrapy 2.18 removeu ``Spider.start_requests()`` da classe base. Um
        método com esse nome deixa de ser chamado automaticamente, fazendo o
        spider encerrar sem realizar nenhuma requisição.
        """
        yield scrapy.Request(
            START_URL,
            dont_filter=True,
            meta={
                "playwright": True,
                "playwright_include_page": True,
                "playwright_page_init_callback": configurar_pagina_busca,
                "playwright_page_methods": [
                    # Espera até existir pelo menos um link dentro de
                    # #noticias-list — só acontece depois que o JS busca e
                    # injeta os resultados no DOM.
                    PageMethod(
                        "wait_for_selector",
                        SELETOR_LINKS_NOTICIA_DOM,
                        timeout=TIMEOUT_ESPERA_MS,
                    ),
                ],
            },
            callback=self.parse,
            errback=self.on_erro,
        )

    async def parse(self, response: TextResponse):
        page = response.meta["playwright_page"]
        pagina_num = 1
        total_itens_gerados = 0
        total_resultados_indicado = None

        try:
            while True:
                html = await page.content()
                sel = Selector(text=html)
                noticias = extrair_noticias_de_selector(sel)
                links = [noticia["href"] for noticia in noticias]

                qtd_texto = sel.css(f"{SELETOR_QTD_RESULTADOS}::text").get()
                if total_resultados_indicado is None and qtd_texto:
                    match_total = re.search(r"\d+", qtd_texto)
                    if match_total:
                        total_resultados_indicado = int(match_total.group())
                self.logger.info(
                    "Página %d: %d links de notícia encontrados (indicador "
                    "'#qtd-resultados': %r)",
                    pagina_num, len(links), (qtd_texto or "").strip(),
                )

                if not links and pagina_num == 1:
                    self.logger.error(
                        "Nenhum link encontrado em '%s' mesmo após esperar o "
                        "JavaScript renderizar. Abra a página com o DevTools, "
                        "confirme o seletor real dos links dentro de "
                        "#noticias-list e ajuste SELETOR_LINKS_NOTICIA em "
                        "scraper/spiders/ufrn_eaj.py.",
                        SELETOR_LISTA_NOTICIAS,
                    )
                    break

                if not links:
                    self.logger.warning(
                        "A página %d terminou de renderizar sem notícias. "
                        "A paginação será encerrada porque as páginas seguintes "
                        "são mais antigas.",
                        pagina_num,
                    )
                    break

                for noticia in noticias:
                    ano = noticia["ano"]
                    if ano is None or not ANO_INICIAL <= ano <= ANO_FINAL:
                        continue

                    # O HTML define <base href="/"> e os hrefs começam por
                    # "imprensa/..." (sem barra inicial). No navegador eles
                    # são relativos à raiz; usar response.url duplicaria o
                    # trecho "/imprensa/noticias/".
                    url_absoluta = resolver_url_noticia(noticia["href"])
                    total_itens_gerados += 1
                    yield NoticiaItem(
                        url=url_absoluta,
                        ano=ano,
                        titulo=noticia["titulo"],
                        origem=response.url,
                    )

                if pagina_num >= MAX_PAGINAS:
                    self.logger.warning(
                        "Limite de segurança de %s páginas atingido — "
                        "parando a paginação.", MAX_PAGINAS,
                    )
                    break

                avancou = await self._ir_para_proxima_pagina(page, links)
                if not avancou:
                    self.logger.info(
                        "Paginação concluída na página %d (%d links no "
                        "total).", pagina_num, total_itens_gerados,
                    )
                    break
                pagina_num += 1
        finally:
            await page.close()

        if total_resultados_indicado is not None:
            self.logger.info(
                "O portal informou %d resultados históricos; o recorte de "
                "%d a %d exportou %d notícias.",
                total_resultados_indicado,
                ANO_INICIAL,
                ANO_FINAL,
                total_itens_gerados,
            )

    async def _ir_para_proxima_pagina(self, page, links_pagina_atual: list[str]) -> bool:
        """Clica no botão de próxima página e espera a lista de notícias
        mudar. Retorna False quando não há próxima página (fim da
        paginação) ou o botão não é encontrado/está desabilitado."""
        botao = None
        seletor_usado = None
        for seletor in SELETORES_BOTAO_PROXIMA:
            candidato = await page.query_selector(seletor)
            if candidato:
                visivel = await candidato.is_visible()
                habilitado = await candidato.is_enabled()
                if visivel and habilitado:
                    botao = candidato
                    seletor_usado = seletor
                    break

        if botao is None:
            return False

        primeiro_href_antes = links_pagina_atual[0] if links_pagina_atual else None
        pagina_destino = await botao.get_attribute("data-page")

        await botao.click()
        try:
            if pagina_destino:
                # A paginação é reconstruída somente depois que a consulta
                # termina. Observar a página ativa também funciona quando o
                # resultado seguinte é legitimamente vazio.
                await page.wait_for_function(
                    "(destino) => document.querySelector("
                    "'#noticias-paginacao li.active a'"
                    ")?.dataset.page === destino",
                    arg=pagina_destino,
                    timeout=TIMEOUT_ESPERA_MS,
                )
            else:
                await page.wait_for_function(
                    (
                        "(hrefAnterior) => {"
                        "  const el = document.querySelector(%r);"
                        "  return el && el.getAttribute('href') !== hrefAnterior;"
                        "}"
                    ) % SELETOR_LINKS_NOTICIA_DOM,
                    arg=primeiro_href_antes,
                    timeout=TIMEOUT_ESPERA_MS,
                )
        except Exception:
            self.logger.info(
                "Clique em '%s' não mudou a lista de notícias dentro do "
                "timeout — assumindo fim da paginação.", seletor_usado,
            )
            return False

        return True

    def parse_noticia(self, response: TextResponse, origem: str):
        ano = extract_year_from_html(response)
        titulo = (response.css(f"{SELETOR_TITULO}::text").get() or "").strip()

        if not titulo:
            titulo = (response.css("title::text").get() or "").strip()

        item = NoticiaItem(
            url=response.url,
            ano=ano,
            titulo=titulo,
            origem=origem,
        )
        yield item

    async def on_erro(self, failure):
        page = failure.request.meta.get("playwright_page")
        if page is not None and not page.is_closed():
            await page.close()
        self.logger.error(
            "Falha ao requisitar %s: %s", failure.request.url, failure.value,
        )
