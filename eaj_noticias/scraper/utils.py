"""Funções auxiliares puras, sem dependência do Scrapy, para facilitar testes unitários.

Concentra duas responsabilidades sensíveis do projeto:

1. `extract_year` — extrai o ano de publicação de uma notícia a partir do HTML,
   tentando várias estratégias (meta tags, tags <time>, texto "Publicado em ...",
   datas soltas no texto) e SEM jamais inventar um valor: se nada confiável for
   encontrado, retorna None.
2. `normalize_url` — normaliza uma URL para evitar duplicidades causadas por
   pequenas diferenças de representação (barra final, maiúsculas no host,
   parâmetros de rastreamento, fragmentos "#...", etc.).
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

# Parâmetros que não alteram o conteúdo da notícia e só causariam duplicidade.
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "mc_cid", "mc_eid",
}

_MESES_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}

# dd/mm/yyyy ou dd-mm-yyyy
_RE_DATA_NUMERICA = re.compile(r"\b([0-3]?\d)[/\-]([01]?\d)[/\-](\d{4})\b")

# yyyy-mm-dd (comum em atributos datetime/ISO 8601 de meta tags e <time>).
# Usa lookaround em vez de \b porque o formato ISO costuma ser seguido de
# "T" (ex.: "2023-11-07T14:30:00"), e \b não marca fronteira entre dígito e
# letra (ambos são caracteres de palavra).
_RE_DATA_ISO = re.compile(r"(?<!\d)(\d{4})-([01]\d)-([0-3]\d)(?!\d)")

# "12 de maio de 2024"
_RE_DATA_EXTENSO = re.compile(
    r"\b([0-3]?\d)\s+de\s+(%s)\s+de\s+(\d{4})\b" % "|".join(_MESES_PT.keys()),
    re.IGNORECASE,
)

# Ano isolado, usado apenas em contexto explícito de publicação (ver função).
_RE_ANO = re.compile(r"\b(19|20)\d{2}\b")


def _ano_plausivel(ano: int) -> bool:
    """Descarta anos fora de uma faixa plausível para notícias da UFRN (evita
    capturar números de portaria, CEP, telefone etc. que acidentalmente casem
    com 4 dígitos)."""
    return 2000 <= ano <= 2100


def extract_year_from_text(text: str) -> Optional[int]:
    """Tenta extrair um ano de publicação a partir de um texto livre.

    Ordem de prioridade:
    1. Data ISO (yyyy-mm-dd) — típica de atributos `datetime`/meta tags.
    2. Data por extenso em português ("12 de maio de 2024").
    3. Data numérica dd/mm/yyyy, mas apenas quando aparece próxima da palavra
       "public" (de "publicada em", "publicado em"), para reduzir falsos
       positivos vindos de outras datas citadas na matéria.
    4. Qualquer data numérica dd/mm/yyyy no texto, como último recurso.
    """
    if not text:
        return None

    m = _RE_DATA_ISO.search(text)
    if m:
        ano = int(m.group(1))
        if _ano_plausivel(ano):
            return ano

    m = _RE_DATA_EXTENSO.search(text)
    if m:
        ano = int(m.group(3))
        if _ano_plausivel(ano):
            return ano

    # Data numérica perto de "publicad[ao] em" — maior confiança.
    for m in _RE_DATA_NUMERICA.finditer(text):
        inicio_contexto = max(0, m.start() - 25)
        contexto = text[inicio_contexto:m.start()].lower()
        if "public" in contexto:
            ano = int(m.group(3))
            if _ano_plausivel(ano):
                return ano

    # Último recurso: primeira data numérica válida do texto.
    m = _RE_DATA_NUMERICA.search(text)
    if m:
        ano = int(m.group(3))
        if _ano_plausivel(ano):
            return ano

    return None


def extract_year_from_html(response) -> Optional[int]:
    """Extrai o ano de publicação a partir de uma resposta Scrapy (página da notícia).

    Tenta primeiro fontes estruturadas (meta tags e a tag <time>), que são mais
    confiáveis, e só then cai para busca textual no corpo da página.
    """
    seletores_meta = [
        "meta[property='article:published_time']::attr(content)",
        "meta[name='date']::attr(content)",
        "meta[itemprop='datePublished']::attr(content)",
        "time::attr(datetime)",
    ]
    for sel in seletores_meta:
        valor = response.css(sel).get()
        if valor:
            ano = extract_year_from_text(valor)
            if ano:
                return ano

    # Fallback: procura no texto visível da página (bloco de conteúdo, se
    # existir; senão, a página inteira).
    bloco = response.css("article, .noticia, .conteudo-noticia, main")
    texto = " ".join(bloco.css("::text").getall()) if bloco else ""
    ano = extract_year_from_text(texto)
    if ano:
        return ano

    # Última tentativa: todo o texto da página.
    texto_completo = " ".join(response.css("::text").getall())
    return extract_year_from_text(texto_completo)


def normalize_url(url: str) -> str:
    """Normaliza uma URL para reduzir duplicidades por diferenças cosméticas:
    host em minúsculas, sem fragmento, sem parâmetros de rastreamento, sem
    barra final redundante e com os parâmetros restantes ordenados.
    """
    partes = urlparse(url.strip())

    esquema = partes.scheme.lower()
    host = partes.netloc.lower()

    caminho = partes.path
    if len(caminho) > 1 and caminho.endswith("/"):
        caminho = caminho.rstrip("/")

    query_pares = [
        (k, v) for k, v in parse_qsl(partes.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    query_pares.sort()
    query = urlencode(query_pares)

    return urlunparse((esquema, host, caminho, "", query, ""))
