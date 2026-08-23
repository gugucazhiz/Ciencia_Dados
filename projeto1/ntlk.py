import re

from nltk.corpus import stopwords


STOPWORDS = set(stopwords.words("portuguese"))


def limpar_texto(texto):
    if not texto:
        return ""

    palavras = re.findall(r"\b[\wÀ-ÿ]+\b", texto.lower())
    palavras_filtradas = [
        palavra for palavra in palavras if palavra not in STOPWORDS
    ]
    return " ".join(palavras_filtradas)


def contar_palavra(texto, palavra):
    if not texto or not palavra:
        return 0

    termo = palavra.lower()
    palavras = re.findall(r"\b[\wÀ-ÿ]+\b", texto.lower())
    return sum(1 for item in palavras if item == termo)
