"""Pipelines de processamento dos itens coletados.

Duas responsabilidades, separadas em pipelines distintos para manter cada um
pequeno e testável:

1. NormalizacaoEDedupPipeline — normaliza a URL de cada item e descarta itens
   cuja URL (normalizada) já tenha sido vista nesta execução do spider.
2. ValidacaoAnoPipeline — garante que o item tem um ano válido; quando não
   tem, registra a ocorrência em log (sem inventar um valor) e descarta o
   item do arquivo final, conforme pedido no enunciado do projeto.
"""

import logging

from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem

from scraper.utils import normalize_url

logger = logging.getLogger(__name__)


class NormalizacaoEDedupPipeline:
    """Normaliza a URL do item e remove duplicatas."""

    def __init__(self):
        self.urls_vistas = set()

    def process_item(self, item):
        adapter = ItemAdapter(item)
        url_normalizada = normalize_url(adapter["url"])
        adapter["url"] = url_normalizada

        if url_normalizada in self.urls_vistas:
            raise DropItem(f"URL duplicada descartada: {url_normalizada}")

        self.urls_vistas.add(url_normalizada)
        return item


class ValidacaoAnoPipeline:
    """Garante que todo item exportado possui um ano de publicação válido."""

    def process_item(self, item):
        adapter = ItemAdapter(item)
        ano = adapter.get("ano")

        if not ano:
            logger.warning(
                "Ano não encontrado para a notícia (URL: %s) — item descartado "
                "do CSV final. Verifique manualmente essa página caso o "
                "número de ocorrências seja alto.",
                adapter.get("url"),
            )
            raise DropItem(f"Ano ausente para {adapter.get('url')}")

        return item
