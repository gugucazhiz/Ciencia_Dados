CREATE TABLE IF NOT EXISTS curso (
  id SERIAL PRIMARY KEY,
  codigo VARCHAR(20) NOT NULL,
  nome TEXT NOT NULL,
  instituicao TEXT,
  versao VARCHAR(10) NOT NULL,
  UNIQUE (codigo, versao)
);
CREATE TABLE IF NOT EXISTS componente (
  id SERIAL PRIMARY KEY,
  curso_id INT NOT NULL REFERENCES curso(id) ON DELETE CASCADE,
  codigo VARCHAR(20) NOT NULL,
  nome TEXT NOT NULL,
  nome_busca TEXT NOT NULL,
  creditos INT,
  carga_horaria INT,
  tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('obrigatoria','optativa','atividade')),
  periodo INT,
  UNIQUE (curso_id, codigo)
);
-- grupo: requisitos com o MESMO grupo são alternativas (OU); grupos diferentes se combinam com E.
CREATE TABLE IF NOT EXISTS prerequisito (
  componente_id INT NOT NULL REFERENCES componente(id) ON DELETE CASCADE,
  requisito_id  INT NOT NULL REFERENCES componente(id) ON DELETE CASCADE,
  grupo INT NOT NULL DEFAULT 1,
  PRIMARY KEY (componente_id, requisito_id),
  CHECK (componente_id <> requisito_id)
);
CREATE INDEX IF NOT EXISTS ix_prereq_requisito ON prerequisito(requisito_id);
CREATE INDEX IF NOT EXISTS ix_comp_nome ON componente(nome_busca);
