"""Camada de acesso aos três bancos + carga genérica a partir de um JSON neutro."""
import os
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import psycopg
from neo4j import GraphDatabase
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pymongo import ASCENDING, MongoClient

CAMPOS = ("codigo", "nome", "creditos", "carga_horaria", "tipo", "periodo", "grupo", "nivel")


def norm(s):
    """minúsculas e sem acentos (busca tolerante)."""
    s = unicodedata.normalize("NFD", (s or "").strip().lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _linha(d):
    return {k: d[k] for k in CAMPOS if d.get(k) is not None}


# ----------------------------------------------------------------- carga genérica
def validar(d):
    cur = d.get("curso") or {}
    for f in ("codigo", "nome", "versao"):
        if not cur.get(f):
            raise ValueError(f"curso.{f} é obrigatório")
    codigos = [c["codigo"] for c in d.get("componentes", [])]
    if len(codigos) != len(set(codigos)):
        raise ValueError("códigos de componente duplicados")
    grafo = defaultdict(list)
    for p in d.get("prerequisitos", []):
        a, b = p["componente"], p["requisito"]
        if a not in codigos or b not in codigos:
            raise ValueError(f"pré-requisito referencia código inexistente: {a} -> {b}")
        if a == b:
            raise ValueError(f"componente exige a si mesmo: {a}")
        grafo[a].append(b)
    visitando, ok = set(), set()

    def dfs(n):
        if n in ok:
            return
        if n in visitando:
            raise ValueError(f"ciclo de pré-requisitos envolvendo {n}")
        visitando.add(n)
        for m in grafo[n]:
            dfs(m)
        visitando.discard(n)
        ok.add(n)

    for c in codigos:
        dfs(c)


def preparar(d):
    validar(d)
    for k in d["componentes"]:
        k["nome_busca"] = norm(k["nome"])
        k.setdefault("periodo", None)
        k.setdefault("creditos", None)
        if k.get("carga_horaria") is None and k["creditos"] is not None:
            k["carga_horaria"] = k["creditos"] * 15  # 1 crédito = 15 h (premissa UFRN)
        k.setdefault("carga_horaria", None)
    for p in d.get("prerequisitos", []):
        p.setdefault("grupo", 1)
    return d


# ----------------------------------------------------------------- PostgreSQL
class Postgres:
    nome = "postgres"

    def __init__(self):
        self._pool = None

    @property
    def pool(self):
        if self._pool is None:
            self._pool = ConnectionPool(
                os.getenv("PG_DSN", "postgresql://tads:tads@localhost:5432/tads"),
                min_size=1, max_size=5, kwargs={"row_factory": dict_row}, open=True,
            )
        return self._pool

    def init(self):
        with self.pool.connection() as c:
            c.execute((Path(__file__).parent / "schema_postgres.sql").read_text(encoding="utf-8"))

    def cursos(self):
        with self.pool.connection() as c:
            return c.execute("SELECT codigo, nome, versao FROM curso ORDER BY codigo, versao").fetchall()

    def carregar(self, d):
        cur = d["curso"]
        with self.pool.connection() as c:
            c.execute("DELETE FROM curso WHERE codigo=%s AND versao=%s", (cur["codigo"], cur["versao"]))
            cid = c.execute(
                "INSERT INTO curso(codigo,nome,instituicao,versao) VALUES (%s,%s,%s,%s) RETURNING id",
                (cur["codigo"], cur["nome"], cur.get("instituicao"), cur["versao"]),
            ).fetchone()["id"]
            ids = {}
            for k in d["componentes"]:
                ids[k["codigo"]] = c.execute(
                    "INSERT INTO componente(curso_id,codigo,nome,nome_busca,creditos,carga_horaria,tipo,periodo)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (cid, k["codigo"], k["nome"], k["nome_busca"], k["creditos"], k["carga_horaria"],
                     k["tipo"], k["periodo"]),
                ).fetchone()["id"]
            for p in d.get("prerequisitos", []):
                c.execute(
                    "INSERT INTO prerequisito(componente_id,requisito_id,grupo) VALUES (%s,%s,%s)",
                    (ids[p["componente"]], ids[p["requisito"]], p["grupo"]),
                )

    COLS = "{a}.codigo, {a}.nome, {a}.creditos, {a}.carga_horaria, {a}.tipo, {a}.periodo"
    FROM = "FROM componente c JOIN curso cu ON cu.id = c.curso_id "
    WHERE = "WHERE cu.codigo = %(curso)s AND cu.versao = %(versao)s "

    def consultar(self, op, curso, versao, arg):
        p = {"curso": curso, "versao": versao, "arg": arg}
        cols = self.COLS.format(a="r")
        if op == "busca":
            p["pat"] = f"%{arg}%"
            p["pre"] = f"{arg}%"
            sql = (f"SELECT {self.COLS.format(a='c')} {self.FROM}{self.WHERE}"
                   "AND (c.nome_busca LIKE %(pat)s OR lower(c.codigo) LIKE %(pre)s) ORDER BY c.codigo")
        elif op == "prerequisitos":
            sql = (f"SELECT {cols}, p.grupo {self.FROM}"
                   "JOIN prerequisito p ON p.componente_id = c.id JOIN componente r ON r.id = p.requisito_id "
                   f"{self.WHERE}AND c.codigo = %(arg)s ORDER BY p.grupo, r.codigo")
        elif op == "dependentes":
            sql = (f"SELECT {cols}, p.grupo {self.FROM}"
                   "JOIN prerequisito p ON p.requisito_id = c.id JOIN componente r ON r.id = p.componente_id "
                   f"{self.WHERE}AND c.codigo = %(arg)s ORDER BY r.codigo")
        elif op == "cadeia":
            sql = f"""
                WITH RECURSIVE cadeia AS (
                  SELECT p.requisito_id AS id, 1 AS nivel
                  {self.FROM}JOIN prerequisito p ON p.componente_id = c.id
                  {self.WHERE}AND c.codigo = %(arg)s
                  UNION
                  SELECT p.requisito_id, ca.nivel + 1
                  FROM cadeia ca JOIN prerequisito p ON p.componente_id = ca.id
                )
                SELECT {cols}, MIN(ca.nivel) AS nivel
                FROM cadeia ca JOIN componente r ON r.id = ca.id
                GROUP BY r.id ORDER BY nivel, r.codigo"""
        else:
            raise ValueError(f"operação inválida: {op}")
        with self.pool.connection() as c:
            return [_linha(r) for r in c.execute(sql, p).fetchall()]


# ----------------------------------------------------------------- MongoDB
class Mongo:
    nome = "mongo"

    def __init__(self):
        self._cli = None

    @property
    def col(self):
        if self._cli is None:
            self._cli = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"),
                                    serverSelectionTimeoutMS=3000)
        return self._cli[os.getenv("MONGO_DB", "tads")]["componentes"]

    def init(self):
        self.col.create_index([("curso.codigo", ASCENDING), ("curso.versao", ASCENDING),
                               ("codigo", ASCENDING)], unique=True)
        self.col.create_index("prerequisitos.codigo")
        self.col.create_index("nome_busca")

    @staticmethod
    def _resumo(k):
        return {f: k.get(f) for f in ("codigo", "nome", "creditos", "carga_horaria", "tipo")}

    def carregar(self, d):
        cur = d["curso"]
        filtro = {"curso.codigo": cur["codigo"], "curso.versao": cur["versao"]}
        self.col.delete_many(filtro)
        por = {k["codigo"]: k for k in d["componentes"]}
        reqs = defaultdict(list)
        for p in d.get("prerequisitos", []):
            reqs[p["componente"]].append(p)
        docs = []
        for k in d["componentes"]:
            pre = [{**self._resumo(por[p["requisito"]]), "grupo": p["grupo"]} for p in reqs[k["codigo"]]]
            docs.append({
                **self._resumo(k), "periodo": k["periodo"], "nome_busca": k["nome_busca"],
                "codigo_busca": k["codigo"].lower(),
                "curso": {"codigo": cur["codigo"], "nome": cur["nome"], "versao": cur["versao"]},
                "prerequisitos": pre, "prereq_codigos": [x["codigo"] for x in pre],
            })
        self.col.insert_many(docs)

    def consultar(self, op, curso, versao, arg):
        f = {"curso.codigo": curso, "curso.versao": versao}
        if op == "busca":
            rx = re.escape(arg)
            docs = self.col.find({**f, "$or": [{"nome_busca": {"$regex": rx}},
                                               {"codigo_busca": {"$regex": "^" + rx}}]}).sort("codigo", 1)
            return [_linha(x) for x in docs]
        if op == "prerequisitos":
            d = self.col.find_one({**f, "codigo": arg}, {"prerequisitos": 1})
            pre = sorted((d or {}).get("prerequisitos", []), key=lambda x: (x["grupo"], x["codigo"]))
            return [_linha(x) for x in pre]
        if op == "dependentes":
            out = []
            for x in self.col.find({**f, "prerequisitos.codigo": arg}).sort("codigo", 1):
                g = next(p["grupo"] for p in x["prerequisitos"] if p["codigo"] == arg)
                out.append(_linha({**x, "grupo": g}))
            return out
        if op == "cadeia":
            r = list(self.col.aggregate([
                {"$match": {**f, "codigo": arg}},
                {"$graphLookup": {"from": "componentes", "startWith": "$prereq_codigos",
                                  "connectFromField": "prereq_codigos", "connectToField": "codigo",
                                  "as": "cadeia", "depthField": "nivel", "restrictSearchWithMatch": f}},
            ]))
            nos = r[0]["cadeia"] if r else []
            nos = [{**x, "nivel": x["nivel"] + 1} for x in nos]
            return [_linha(x) for x in sorted(nos, key=lambda x: (x["nivel"], x["codigo"]))]
        raise ValueError(f"operação inválida: {op}")


# ----------------------------------------------------------------- Neo4j
class Neo4j:
    nome = "neo4j"
    RET = ("k.codigo AS codigo, k.nome AS nome, k.creditos AS creditos, "
           "k.carga_horaria AS carga_horaria, k.tipo AS tipo, k.periodo AS periodo")

    def __init__(self):
        self._drv = None

    @property
    def drv(self):
        if self._drv is None:
            self._drv = GraphDatabase.driver(
                os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASS", "tads12345")))
        return self._drv

    def _run(self, cypher, **p):
        with self.drv.session() as s:
            return [r.data() for r in s.run(cypher, **p)]

    def init(self):
        self._run("CREATE CONSTRAINT componente_chave IF NOT EXISTS "
                  "FOR (k:Componente) REQUIRE k.chave IS UNIQUE")
        self._run("CREATE INDEX componente_codigo IF NOT EXISTS FOR (k:Componente) ON (k.codigo)")
        self._run("CREATE INDEX curso_codigo IF NOT EXISTS FOR (c:Curso) ON (c.codigo)")

    def carregar(self, d):
        cur = d["curso"]
        base = {"cod": cur["codigo"], "ver": cur["versao"]}
        self._run("MATCH (cu:Curso {codigo:$cod, versao:$ver}) "
                  "OPTIONAL MATCH (cu)-[:TEM_COMPONENTE]->(k) DETACH DELETE k, cu", **base)
        self._run("MERGE (cu:Curso {codigo:$cod, versao:$ver}) SET cu.nome=$nome "
                  "WITH cu UNWIND $comps AS k "
                  "CREATE (cu)-[:TEM_COMPONENTE]->(:Componente {chave:$cod+'-'+$ver+'-'+k.codigo, "
                  "codigo:k.codigo, nome:k.nome, nome_busca:k.nome_busca, creditos:k.creditos, "
                  "carga_horaria:k.carga_horaria, tipo:k.tipo, periodo:k.periodo})",
                  nome=cur["nome"], comps=d["componentes"], **base)
        if d.get("prerequisitos"):
            self._run("UNWIND $pre AS p "
                      "MATCH (a:Componente {chave:$cod+'-'+$ver+'-'+p.componente}), "
                      "(b:Componente {chave:$cod+'-'+$ver+'-'+p.requisito}) "
                      "CREATE (a)-[:REQUER {grupo:p.grupo}]->(b)", pre=d["prerequisitos"], **base)

    def consultar(self, op, curso, versao, arg):
        p = {"curso": curso, "versao": versao, "arg": arg}
        cu = "(:Curso {codigo:$curso, versao:$versao})-[:TEM_COMPONENTE]->"
        if op == "busca":
            q = (f"MATCH {cu}(k:Componente) WHERE k.nome_busca CONTAINS $arg "
                 f"OR toLower(k.codigo) STARTS WITH $arg RETURN {self.RET} ORDER BY codigo")
        elif op == "prerequisitos":
            q = (f"MATCH {cu}(c:Componente {{codigo:$arg}})-[r:REQUER]->(k:Componente) "
                 f"RETURN {self.RET}, r.grupo AS grupo ORDER BY grupo, codigo")
        elif op == "dependentes":
            q = (f"MATCH {cu}(c:Componente {{codigo:$arg}}) "
                 f"MATCH (k:Componente)-[r:REQUER]->(c) "
                 f"RETURN {self.RET}, r.grupo AS grupo ORDER BY codigo")
        elif op == "cadeia":
            q = (f"MATCH {cu}(c:Componente {{codigo:$arg}}) "
                 f"MATCH path = (c)-[:REQUER*1..15]->(k:Componente) "
                 f"RETURN {self.RET}, min(length(path)) AS nivel ORDER BY nivel, codigo")
        else:
            raise ValueError(f"operação inválida: {op}")
        return [_linha(r) for r in self._run(q, **p)]


REPOS = {"postgres": Postgres(), "mongo": Mongo(), "neo4j": Neo4j()}


def carregar_tudo(d):
    """Valida e grava o mesmo JSON nos três bancos. Retorna status por banco."""
    d = preparar(d)
    status = {}
    for nome, repo in REPOS.items():
        try:
            repo.init()
            repo.carregar(d)
            status[nome] = "ok"
        except Exception as e:  # um banco fora do ar não impede os outros
            status[nome] = f"erro: {e}"
    return status
