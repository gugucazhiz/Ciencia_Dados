import statistics
import time

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .repos import REPOS, carregar_tudo, norm

app = FastAPI(title="Estrutura curricular — consulta em 3 bancos")
OPS = {"busca", "prerequisitos", "dependentes", "cadeia"}


def _arg(op, q):
    return norm(q) if op == "busca" else q.strip().upper()


def executar(db, op, curso, versao, q):
    if db not in REPOS or op not in OPS:
        raise HTTPException(400, "db ou op inválido")
    t0 = time.perf_counter()
    rows = REPOS[db].consultar(op, curso, versao, _arg(op, q))
    ms = (time.perf_counter() - t0) * 1000  # tempo da consulta + leitura do resultado
    return {"db": db, "op": op, "tempo_ms": round(ms, 2), "total": len(rows), "resultados": rows}


@app.get("/api/cursos")
def cursos():
    try:
        return REPOS["postgres"].cursos()
    except Exception as e:
        raise HTTPException(503, f"postgres indisponível: {e}")


@app.get("/api/consulta")
def consulta(db: str, op: str, q: str = "", curso: str = "TADS", versao: str = "2019"):
    try:
        return executar(db, op, curso, versao, q)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"{db}: {e}")


@app.get("/api/benchmark")
def benchmark(op: str, q: str = "", curso: str = "TADS", versao: str = "2019", n: int = 30):
    """Roda a mesma consulta n vezes em cada banco (3 execuções de aquecimento descartadas)."""
    n = max(5, min(n, 200))
    out = {}
    for db in REPOS:
        try:
            for _ in range(3):
                executar(db, op, curso, versao, q)
            t = sorted(executar(db, op, curso, versao, q)["tempo_ms"] for _ in range(n))
            out[db] = {"media_ms": round(statistics.mean(t), 2), "mediana_ms": round(statistics.median(t), 2),
                       "min_ms": t[0], "p95_ms": t[int(0.95 * (n - 1))], "execucoes": n}
        except Exception as e:
            out[db] = {"erro": str(e)}
    return out


@app.post("/api/importar")
def importar(dados: dict = Body(...)):
    """Cadastra outro curso/versão: mesmo JSON do data/tads_2019.json."""
    try:
        return carregar_tudo(dados)
    except ValueError as e:
        raise HTTPException(422, str(e))


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")
