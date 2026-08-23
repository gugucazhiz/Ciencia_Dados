# utils/wikipedia.py
from urllib.parse import quote
import requests
from bs4 import BeautifulSoup

WIKI_BASE = "https://pt.wikipedia.org"


def _sentence_case(termo):
    palavras = termo.split()
    if not palavras:
        return ""
    return palavras[0].capitalize() + " " + " ".join(p.lower() for p in palavras[1:])


def _url_wikipedia(termo_formatado):
    return f"{WIKI_BASE}/wiki/{quote(termo_formatado.replace(' ', '_'), safe='_')}"


def _pagina_existe(url, timeout=5):
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200:
            return True
        if resp.status_code in (404, 405):
            resp = requests.get(url, timeout=timeout, allow_redirects=True)
            return resp.status_code == 200
        return False
    except requests.RequestException:
        return False


def _buscar_via_pesquisa(termo, timeout=5):
    """Guardrail final: usa a página de busca HTML do Wikipédia (não a API)
    pra achar o artigo mais provável quando a URL direta falha."""
    try:
        resp = requests.get(
            f"{WIKI_BASE}/w/index.php",
            params={"search": termo, "fulltext": "1"},
            timeout=timeout,
            allow_redirects=True,
        )
    except requests.RequestException:
        return None

    if resp.status_code != 200:
        return None

    # o MediaWiki às vezes já redireciona direto pro artigo único
    if "/wiki/" in resp.url and "Especial:Pesquisar" not in resp.url:
        return resp.url

    soup = BeautifulSoup(resp.text, "html.parser")
    primeiro = soup.select_one("div.mw-search-result-heading a")
    if primeiro and primeiro.get("href"):
        return WIKI_BASE + primeiro["href"]

    return None


def resolver_url_wikipedia(termo_original):
    """Retorna (url, encontrado). Tenta variantes antes de desistir."""
    termo = termo_original.strip().replace("_", " ")
    if not termo:
        return None, False

    for candidato in {_sentence_case(termo), termo}:
        if not candidato:
            continue
        url = _url_wikipedia(candidato)
        if _pagina_existe(url):
            return url, True

    url_busca = _buscar_via_pesquisa(termo)
    if url_busca:
        return url_busca, True

    return None, False