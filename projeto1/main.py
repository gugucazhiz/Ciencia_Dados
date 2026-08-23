import re
from urllib.parse import quote, urlparse
import numpy as np
from PIL import Image, ImageDraw
import requests
import streamlit as st

from beautifulSoup import scraping_requests
from ntlk import contar_palavra, limpar_texto
from scrapy import scrapy_scrape

import matplotlib.pyplot as plt
from wordcloud import WordCloud

CONECTIVOS_MINUSCULOS = {
    "de", "da", "do", "das", "dos", "e", "em", "a", "o", "as", "os",
    "para", "com", "no", "na", "nos", "nas", "por",
}

HEADERS = {
    "User-Agent": "ComparadorWebScraping/1.0 (uso educacional)"
}


def _normalizar_sentence_case(termo: str) -> str:
    palavras = termo.strip().replace("_", " ").split()
    if not palavras:
        return ""
    corpo = palavras[0].capitalize() + " " + " ".join(
        p.lower() for p in palavras[1:]
    )
    return corpo.replace(" ", "_")


def _normalizar_title_case(termo: str) -> str:
    palavras = termo.strip().replace("_", " ").split()
    if not palavras:
        return ""
    resultado = []
    for i, palavra in enumerate(palavras):
        if i > 0 and palavra.lower() in CONECTIVOS_MINUSCULOS:
            resultado.append(palavra.lower())
        else:
            resultado.append(palavra.capitalize())
    return "_".join(resultado)


def _normalizar_como_digitado(termo: str) -> str:
    return termo.strip().replace(" ", "_")


def _gerar_candidatos(termo: str):
    candidatos = [
        _normalizar_sentence_case(termo),
        _normalizar_title_case(termo),
        _normalizar_como_digitado(termo),
        termo.strip().replace("_", " ").title().replace(" ", "_"),
    ]
    vistos = set()
    unicos = []
    for c in candidatos:
        if c and c not in vistos:
            vistos.add(c)
            unicos.append(c)
    return unicos

def _gerar_mascara_nuvem(largura=800, altura=500):
    """Gera uma máscara em forma de nuvem desenhando círculos sobrepostos."""
    img = Image.new("L", (largura, altura), color=255)  # fundo branco
    draw = ImageDraw.Draw(img)

    # círculos (x_centro, y_centro, raio) formando o contorno de uma nuvem
    circulos = [
        (largura * 0.30, altura * 0.55, largura * 0.16),
        (largura * 0.45, altura * 0.40, largura * 0.19),
        (largura * 0.62, altura * 0.45, largura * 0.20),
        (largura * 0.78, altura * 0.55, largura * 0.15),
        (largura * 0.50, altura * 0.60, largura * 0.22),
        (largura * 0.35, altura * 0.65, largura * 0.15),
        (largura * 0.65, altura * 0.65, largura * 0.15),
    ]

    for x, y, r in circulos:
        draw.ellipse(
            [x - r, y - r, x + r, y + r],
            fill=0,  # preto = área onde as palavras entram
        )

    return np.array(img)


def gerar_wordcloud(texto, titulo="Nuvem de palavras"):
    if not texto or not texto.strip():
        return None

    mascara = _gerar_mascara_nuvem()

    wc = WordCloud(
        width=800,
        height=500,
        background_color="white",
        colormap="viridis",
        mask=mascara,
        contour_width=2,
        contour_color="steelblue",
        max_words=100,
    ).generate(texto)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    ax.set_title(titulo)
    return fig

def _url_existe(session: requests.Session, url: str) -> bool:
    try:
        resp = session.head(url, headers=HEADERS, timeout=8, allow_redirects=True)
        if resp.status_code == 405:  # alguns servidores não aceitam HEAD
            resp = session.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def _buscar_via_pagina_de_busca(session: requests.Session, termo: str):
    """Fallback: usa a página de busca em HTML (index.php), não a API.
    Se a busca redirecionar direto para um artigo, retorna essa URL."""
    try:
        resp = session.get(
            "https://pt.wikipedia.org/w/index.php",
            params={"search": termo, "title": "Especial:Pesquisar", "fulltext": "1"},
            headers=HEADERS,
            timeout=8,
            allow_redirects=True,
        )
    except requests.RequestException:
        return None

    if resp.status_code != 200:
        return None

    caminho = urlparse(resp.url).path
    if "/wiki/" in caminho and "Especial:Pesquisar" not in resp.url:
        return resp.url

    return None


def resolver_url_wikipedia(termo: str, session: requests.Session):
    candidato_original = f"https://pt.wikipedia.org/wiki/{quote(_normalizar_sentence_case(termo), safe='_')}"

    for candidato in _gerar_candidatos(termo):
        url = f"https://pt.wikipedia.org/wiki/{quote(candidato, safe='_')}"
        if _url_existe(session, url):
            foi_corrigido = url != candidato_original
            return url, foi_corrigido

    url_busca = _buscar_via_pagina_de_busca(session, termo)
    if url_busca:
        return url_busca, True

    return None, False

st.title("Comparador de Web Scraping")

termos = st.text_area(
    placeholder=(
        "Universidade Federal do Rio Grande do Norte, "
        "Ciência de Dados, "
        "Aprendizado de Máquina, "
        "Engenharia de Software, "
        "Armazém de Dados"
    ),
)

palavra = st.text_input("Digite a palavra que deseja pesquisar")


if st.button("Executar Scraping"):

    lista_termos = [
        termo.strip() for termo in termos.split(",") if termo.strip()
    ]

    if len(lista_termos) != 5:
        st.error("Digite exatamente 5 termos.")
        st.stop()

    if not palavra.strip():
        st.error("Digite uma palavra para pesquisar.")
        st.stop()

    st.subheader("Resolvendo páginas na Wikipédia")

    urls_wikipedia = []
    houve_falha = False

    with requests.Session() as session:
        with st.spinner("Validando links..."):
            for termo in lista_termos:
                url, foi_corrigido = resolver_url_wikipedia(termo, session)

                if url is None:
                    st.error(
                        f"Não foi possível encontrar uma página da Wikipédia "
                        f"para **{termo}**. Verifique a grafia do termo."
                    )
                    houve_falha = True
                    continue

                if foi_corrigido:
                    st.info(f"**{termo}** → título corrigido automaticamente")

                st.write(f"**{termo}**")
                st.code(url)
                urls_wikipedia.append(url)

    if houve_falha:
        st.stop()

    try:
        texto_requests, tempo_requests = scraping_requests(urls_wikipedia)
        texto_scrapy, tempo_scrapy = scrapy_scrape(urls_wikipedia)
    except Exception as erro:
        st.error(f"Erro durante o scraping: {erro}")
        st.stop()

    texto_limpo_requests = limpar_texto(texto_requests)
    texto_limpo_scrapy = limpar_texto(texto_scrapy)

    ocorrencias_requests = contar_palavra(texto_limpo_requests, palavra)
    ocorrencias_scrapy = contar_palavra(texto_limpo_scrapy, palavra)

    st.subheader("Resultados")

    col1, col2 = st.columns(2)

    
    with col1:
        st.metric("Requests + BeautifulSoup", f"{tempo_requests:.2f} s")
        st.write(f"Ocorrências: {ocorrencias_requests}")

    with col2:
        st.metric("Scrapy", f"{tempo_scrapy:.2f} s")
        st.write(f"Ocorrências: {ocorrencias_scrapy}")

    st.subheader("Nuvens de palavras")

    col1, col2 = st.columns(2)

    with col1:
        fig_requests = gerar_wordcloud(
            texto_limpo_requests, "Requests + BeautifulSoup"
        )
        if fig_requests:
            st.pyplot(fig_requests)
        else:
            st.info("Sem texto suficiente para gerar a nuvem.")

    with col2:
        fig_scrapy = gerar_wordcloud(
            texto_limpo_scrapy, "Scrapy"
        )
        if fig_scrapy:
            st.pyplot(fig_scrapy)
        else:
            st.info("Sem texto suficiente para gerar a nuvem.")