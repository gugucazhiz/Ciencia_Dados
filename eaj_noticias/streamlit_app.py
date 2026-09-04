"""Dashboard Streamlit — Notícias da EAJ/UFRN por ano.

Lê o CSV gerado pelo spider Scrapy (data/noticias_eaj.csv) e apresenta:
- quantidade de notícias por ano (gráfico de barras);
- métricas gerais (total de notícias, anos analisados, ano com mais notícias);
- tabela com os dados coletados (ano + URL).

Execução: streamlit run streamlit_app.py
"""

from pathlib import Path

import pandas as pd
import streamlit as st

CAMINHO_CSV = Path(__file__).parent / "data" / "noticias_eaj.csv"

st.set_page_config(page_title="Notícias EAJ/UFRN", page_icon="📰", layout="wide")


def carregar_dados(caminho: Path) -> pd.DataFrame:
    """Carrega e valida o CSV gerado pelo scraper.

    Mantém apenas linhas com ano numérico válido — o spider já filtra isso
    antes de exportar, mas validamos de novo aqui para o dashboard nunca
    quebrar com um CSV editado manualmente ou incompleto.
    """
    try:
        df = pd.read_csv(caminho, dtype={"url": str})
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=["ano", "url", "titulo"])
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce")
    df = df.dropna(subset=["ano", "url"])
    df["ano"] = df["ano"].astype(int)
    df = df.drop_duplicates(subset=["url"])
    return df


def main() -> None:
    st.title("📰 Notícias da EAJ/UFRN")
    st.caption(
        "Quantidade de notícias do portal da UFRN que mencionam a EAJ "
        "(Escola Agrícola de Jundiaí), por ano de publicação."
    )

    if not CAMINHO_CSV.exists():
        st.error(
            f"Arquivo de dados não encontrado em `{CAMINHO_CSV}`.\n\n"
            "Rode o scraper primeiro com `scrapy crawl ufrn_eaj` "
            "(a partir da raiz do projeto) para gerá-lo."
        )
        st.stop()

    df = carregar_dados(CAMINHO_CSV)

    if df.empty:
        st.warning(
            "O arquivo de dados existe, mas está vazio ou não contém "
            "registros válidos (ano + URL). Verifique o log da última "
            "execução do scraper — nenhum dado fictício é exibido aqui."
        )
        st.stop()

    contagem_por_ano = df.groupby("ano").size().sort_index()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total de notícias", int(contagem_por_ano.sum()))
    col2.metric("Anos analisados", int(contagem_por_ano.shape[0]))
    ano_top = int(contagem_por_ano.idxmax())
    col3.metric("Ano com mais notícias", ano_top, f"{int(contagem_por_ano.max())} notícias")

    anos_disponiveis = sorted(contagem_por_ano.index.tolist(), reverse=True)
    ano_selecionado = col4.selectbox("Ano selecionado", anos_disponiveis)
    col4.metric(
        f"Notícias em {ano_selecionado}",
        int(contagem_por_ano.loc[ano_selecionado]),
    )

    st.subheader("Quantidade de notícias por ano")
    st.bar_chart(contagem_por_ano)

    st.subheader(f"Notícias de {ano_selecionado}")
    st.dataframe(
        df[df["ano"] == ano_selecionado][["ano", "titulo", "url"]]
        if "titulo" in df.columns
        else df[df["ano"] == ano_selecionado][["ano", "url"]],
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("Ver todos os dados coletados"):
        colunas = [c for c in ["ano", "titulo", "url"] if c in df.columns]
        st.dataframe(
            df[colunas].sort_values("ano", ascending=False),
            use_container_width=True,
            hide_index=True,
        )


if __name__ == "__main__":
    main()
