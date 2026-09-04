"""Testes unitários das funções em scraper/utils.py.

Executar com: pytest tests/ -v
Não dependem de rede nem do Scrapy rodando — só das funções puras.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.utils import extract_year_from_text, normalize_url


def test_data_numerica_simples():
    assert extract_year_from_text("Publicada em 12/05/2024 às 10h") == 2024


def test_data_iso():
    assert extract_year_from_text("2023-11-07T14:30:00-03:00") == 2023


def test_data_por_extenso():
    assert extract_year_from_text("Notícia de 3 de março de 2022 sobre a EAJ") == 2022


def test_prioriza_contexto_publicacao_sobre_outras_datas():
    texto = (
        "O evento citado ocorreu em 01/01/2020, mas a notícia foi "
        "publicada em 15/06/2025."
    )
    assert extract_year_from_text(texto) == 2025


def test_sem_data_retorna_none():
    assert extract_year_from_text("Texto sem nenhuma data reconhecível.") is None


def test_ano_implausivel_e_ignorado():
    # "99/99/9999" não deve casar (mês/dia inválidos no regex) e não deve
    # gerar um ano fora da faixa plausível.
    assert extract_year_from_text("Código do processo: 12/34/9999") is None


def test_normaliza_barra_final():
    assert normalize_url("https://www.ufrn.br/noticia/123/") == normalize_url(
        "https://www.ufrn.br/noticia/123"
    )


def test_normaliza_maiusculas_no_host():
    assert normalize_url("https://WWW.UFRN.br/noticia/123") == normalize_url(
        "https://www.ufrn.br/noticia/123"
    )


def test_normaliza_remove_parametros_de_rastreamento():
    a = normalize_url("https://www.ufrn.br/noticia/123?utm_source=twitter")
    b = normalize_url("https://www.ufrn.br/noticia/123")
    assert a == b


def test_normaliza_remove_fragmento():
    a = normalize_url("https://www.ufrn.br/noticia/123#comentarios")
    b = normalize_url("https://www.ufrn.br/noticia/123")
    assert a == b


def test_normaliza_preserva_query_relevante():
    url = normalize_url("https://www.ufrn.br/noticia?id=123")
    assert "id=123" in url


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
