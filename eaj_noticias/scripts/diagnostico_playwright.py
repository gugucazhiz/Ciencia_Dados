"""Script de diagnóstico rápido, independente do Scrapy: abre a página de
busca da EAJ num Chromium headless real, espera o JS renderizar e imprime
quantos links de notícia foram encontrados — útil para validar rapidamente
os seletores antes de rodar o crawl completo.

Uso (com o ambiente virtual do projeto ativado e `playwright install
chromium` já executado):

    python scripts/diagnostico_playwright.py
"""

import asyncio
from urllib.parse import urljoin

from playwright.async_api import async_playwright

URL = "https://www.ufrn.br/imprensa/noticias/filtros?keyword=EAJ"


async def main() -> None:
    async with async_playwright() as p:
        navegador = await p.chromium.launch(headless=True)
        pagina = await navegador.new_page()

        print(f"Abrindo {URL} ...")
        await pagina.goto(URL, timeout=30_000)

        print("Esperando o JavaScript popular #noticias-list ...")
        try:
            await pagina.wait_for_selector(
                "#noticias-list .noticia h2 a.blue-link[href]",
                timeout=45_000,
            )
        except Exception as exc:
            print(f"TIMEOUT esperando os resultados aparecerem: {exc}")
            print(
                "Isso pode indicar que o seletor mudou, que a busca não "
                "retornou resultados, ou que a página mudou de estrutura. "
                "Rode com headless=False (edite este script) para observar "
                "visualmente o que acontece."
            )
            await navegador.close()
            return

        links = await pagina.eval_on_selector_all(
            "#noticias-list .noticia h2 a.blue-link[href]",
            "els => els.map(e => e.getAttribute('href'))",
        )
        qtd_texto = await pagina.text_content("#qtd-resultados")

        print(f"Indicador '#qtd-resultados': {qtd_texto!r}")
        print(f"Links encontrados na 1ª página: {len(links)}")
        for href in links:
            print(f"  - {href}")

        # Testa também a extração de data numa notícia real, se achou alguma.
        if links:
            primeira_url = urljoin("https://www.ufrn.br/", links[0])
            print(f"\nAbrindo a primeira notícia para checar #date_create: {primeira_url}")
            await pagina.goto(primeira_url, timeout=30_000)
            try:
                await pagina.wait_for_function(
                    "() => { const el = document.querySelector('#date_create'); "
                    "return el && el.textContent.trim().length > 0; }",
                    timeout=45_000,
                )
                data_texto = await pagina.text_content("#date_create")
                titulo_texto = await pagina.text_content("h1.sec-title")
                print(f"  Título: {titulo_texto!r}")
                print(f"  Data:   {data_texto!r}")
            except Exception as exc:
                print(f"  TIMEOUT esperando #date_create ser preenchido: {exc}")

        await navegador.close()


if __name__ == "__main__":
    asyncio.run(main())
