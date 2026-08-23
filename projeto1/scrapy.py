import time

import requests
from bs4 import BeautifulSoup


def scrapy_scrape(urls):
    textos = []
    iniciar_timer = time.perf_counter()

    for url in urls:
        resposta = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resposta.raise_for_status()

        sopa = BeautifulSoup(resposta.text, "html.parser")

        for elemento in sopa([
            "script",
            "style",
            "nav",
            "footer",
            "header",
        ]):
            elemento.decompose()

        texto = sopa.get_text(separator=" ", strip=True)
        textos.append(texto)

    texto_completo = " ".join(textos)
    terminar_timer = time.perf_counter()
    tempo_total = terminar_timer - iniciar_timer

    return texto_completo, tempo_total
