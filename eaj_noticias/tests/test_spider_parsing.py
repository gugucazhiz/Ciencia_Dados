"""Valida, com HTML sintético local, as partes do spider que NÃO dependem de
um navegador real (extração de links, extração de ano/título na página de
notícia). A orquestração via Playwright (clicar em "próxima página", esperar
o JS renderizar) não é testável sem um Chromium de verdade — para isso, use
o script de diagnóstico manual (scripts/diagnostico_playwright.py) contra o
site real, com internet disponível.

Executar com: pytest tests/test_spider_parsing.py -v
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapy.http import HtmlResponse, Request
from scrapy.selector import Selector

from scraper.spiders.ufrn_eaj import (
    UfrnEajSpider,
    extrair_links_de_selector,
    extrair_noticias_de_selector,
    resolver_url_noticia,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _selector_from_fixture(nome_arquivo: str) -> Selector:
    caminho = os.path.join(FIXTURES_DIR, nome_arquivo)
    with open(caminho, "r", encoding="utf-8") as f:
        return Selector(text=f.read())


def _response_from_fixture(nome_arquivo: str, url: str) -> HtmlResponse:
    caminho = os.path.join(FIXTURES_DIR, nome_arquivo)
    with open(caminho, "rb") as f:
        corpo = f.read()
    return HtmlResponse(url=url, body=corpo, request=Request(url=url))


def test_extrai_e_dedup_links_de_noticia():
    sel = _selector_from_fixture("listagem_pagina1.html")
    links = extrair_links_de_selector(sel)

    assert links == [
        "imprensa/noticias/1001/eaj-realiza-evento-2024",
        "imprensa/noticias/1002/eaj-lanca-projeto-2023",
    ]


def test_resolve_link_relativo_a_raiz_do_portal():
    assert resolver_url_noticia(
        "imprensa/noticias/1001/eaj-realiza-evento-2024"
    ) == "https://www.ufrn.br/imprensa/noticias/1001/eaj-realiza-evento-2024"


def test_extrai_ano_titulo_e_link_da_listagem_renderizada():
    sel = _selector_from_fixture("listagem_pagina1.html")

    noticias = extrair_noticias_de_selector(sel)

    assert noticias == [
        {
            "href": "imprensa/noticias/1001/eaj-realiza-evento-2024",
            "titulo": "EAJ realiza evento",
            "ano": 2024,
        },
        {
            "href": "imprensa/noticias/1002/eaj-lanca-projeto-2023",
            "titulo": "EAJ lança projeto",
            "ano": 2023,
        },
    ]


def test_extrai_ano_e_titulo_da_pagina_de_noticia():
    spider = UfrnEajSpider()
    response = _response_from_fixture(
        "noticia_1001.html",
        "https://www.ufrn.br/imprensa/noticias/1001/eaj-realiza-evento-2024",
    )

    itens = list(
        spider.parse_noticia(
            response, origem="https://www.ufrn.br/imprensa/noticias/filtros?keyword=EAJ"
        )
    )

    assert len(itens) == 1
    assert itens[0]["ano"] == 2024
    assert "EAJ realiza evento" in itens[0]["titulo"]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
