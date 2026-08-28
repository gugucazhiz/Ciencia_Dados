from beautifulSoup import scraping_requests
from ntlk import limpar_texto, contar_palavra


class FakeResponse:
    def __init__(self, html):
        self.text = html

    def raise_for_status(self):
        return None


def test_scraping_requests_removes_scripts_and_returns_text(monkeypatch):
    html = """
    <html>
      <body>
        <script>var x = 1;</script>
        <style>.x { color: red; }</style>
        <header>cabecalho</header>
        <nav>menu</nav>
        <p>Ciência de Dados</p>
        <footer>rodape</footer>
      </body>
    </html>
    """

    def fake_get(url, timeout, headers):
        assert url == "https://example.com"
        assert timeout == 10
        assert headers["User-Agent"]
        return FakeResponse(html)

    monkeypatch.setattr("requests.get", fake_get)

    texto, tempo = scraping_requests(["https://example.com"])

    assert "var x = 1" not in texto.lower()
    assert "cabecalho" not in texto.lower()
    assert "ciência de dados" in texto.lower()
    assert tempo <= 0


def test_limpar_texto_e_contar_palavra():
    texto = "Ciência de Dados e Dados"

    limpo = limpar_texto(texto)
    assert limpo == "ciência dados dados"
    assert contar_palavra(limpo, "dados") == 2


def test_validar_quantidade_de_termos():
    import main

    assert main.parsear_termos("Ciência de Dados") == ["Ciência de Dados"]
    assert main.parsear_termos("A, B, C, D") == ["A", "B", "C", "D"]
    assert main.parsear_termos("A, B, C, D, E") == ["A", "B", "C", "D", "E"]

    try:
        main.parsear_termos("")
        assert False, "Deveria rejeitar entrada vazia"
    except ValueError:
        pass

    try:
        main.parsear_termos("A, B, C, D, E, F")
        assert False, "Deveria rejeitar mais de 5 termos"
    except ValueError:
        pass
