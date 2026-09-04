"""Itens coletados pelo spider de notícias da EAJ/UFRN."""

import scrapy


class NoticiaItem(scrapy.Item):
    """Representa uma notícia encontrada na busca por 'EAJ' no portal da UFRN."""

    # URL canônica (normalizada) da notícia.
    url = scrapy.Field()

    # Ano de publicação, extraído a partir da própria página da notícia.
    ano = scrapy.Field()

    # Título da notícia (opcional, útil para depuração e para o dashboard).
    titulo = scrapy.Field()

    # URL da página de listagem/busca de onde a notícia foi descoberta.
    # Útil para depuração quando a extração de ano falha.
    origem = scrapy.Field()
