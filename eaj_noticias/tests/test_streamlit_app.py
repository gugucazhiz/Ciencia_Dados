"""Testes do carregamento de dados usado pelo dashboard Streamlit."""

from streamlit_app import carregar_dados


def test_csv_vazio_retorna_dataframe_vazio(tmp_path):
    caminho = tmp_path / "noticias.csv"
    caminho.touch()

    df = carregar_dados(caminho)

    assert df.empty
    assert list(df.columns) == ["ano", "url", "titulo"]
