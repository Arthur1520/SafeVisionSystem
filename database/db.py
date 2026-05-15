"""
Banco de dados SQLite - Sistema de Fiscalizacao de EPIs
Mesmas colunas do MySQL, agora em SQLite (sem instalacao extra).
"""

import sqlite3
import datetime
import hashlib
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "epi_sistema.db")


def _conectar():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar_banco():
    conn = _conectar()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nome      TEXT NOT NULL,
            usuario   TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            ativo     INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS cameras (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id   TEXT NOT NULL UNIQUE,
            descricao   TEXT,
            localizacao TEXT,
            ativa       INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS ocorrencias (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora     TEXT NOT NULL,
            camera_id     TEXT NOT NULL,
            epis_ausentes TEXT NOT NULL,
            imagem_base64 TEXT,
            revisado      INTEGER DEFAULT 0,
            criado_em     TEXT DEFAULT (datetime('now','localtime'))
        );
    """)

    # Admin padrao: admin / admin123
    senha_hash = hashlib.sha256("admin123".encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO usuarios (nome, usuario, senha_hash) VALUES (?,?,?)",
              ("Administrador", "admin", senha_hash))

    c.execute("INSERT OR IGNORE INTO cameras (camera_id, descricao, localizacao) VALUES (?,?,?)",
              ("cam_01", "Camera Principal", "Entrada"))

    conn.commit()
    conn.close()
    print("[BD] SQLite inicializado com sucesso:", DB_PATH)


class DatabaseManager:
    def __init__(self):
        inicializar_banco()

    def inserir_ocorrencia(self, ocorrencia: dict) -> int:
        conn = _conectar()
        try:
            c = conn.cursor()
            c.execute(
                "INSERT INTO ocorrencias (data_hora, camera_id, epis_ausentes, imagem_base64) VALUES (?,?,?,?)",
                (
                    str(ocorrencia["data_hora"].strftime("%d/%m/%Y %H:%M:%S")),
                    ocorrencia["camera_id"],
                    ocorrencia["epis_ausentes"],
                    ocorrencia["imagem_base64"],
                )
            )
            conn.commit()
            return c.lastrowid
        finally:
            conn.close()

    def listar_ocorrencias(self, limite=50, offset=0, camera_id=None,
                           data_inicio=None, data_fim=None, epi_filtro=None):
        conn = _conectar()
        try:
            c = conn.cursor()
            sql = "SELECT id, data_hora, camera_id, epis_ausentes, revisado, criado_em FROM ocorrencias WHERE 1=1"
            params = []

            if camera_id:
                sql += " AND camera_id = ?"
                params.append(camera_id)
            if data_inicio:
                sql += " AND data_hora >= ?"
                params.append(data_inicio)
            if data_fim:
                sql += " AND data_hora <= ?"
                params.append(data_fim + " 23:59:59")
            if epi_filtro:
                sql += " AND epis_ausentes LIKE ?"
                params.append(f"%{epi_filtro}%")

            sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
            params += [limite, offset]

            c.execute(sql, params)
            return [dict(row) for row in c.fetchall()]
        finally:
            conn.close()

    def obter_ocorrencia(self, ocorrencia_id: int):
        conn = _conectar()
        try:
            c = conn.cursor()
            c.execute("SELECT * FROM ocorrencias WHERE id = ?", (ocorrencia_id,))
            row = c.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def contar_ocorrencias(self, camera_id=None, data_inicio=None, data_fim=None, epi_filtro=None):
        conn = _conectar()
        try:
            c = conn.cursor()
            sql = "SELECT COUNT(*) as n FROM ocorrencias WHERE 1=1"
            params = []
            if camera_id:
                sql += " AND camera_id = ?"
                params.append(camera_id)
            if data_inicio:
                sql += " AND data_hora >= ?"
                params.append(data_inicio)
            if data_fim:
                sql += " AND data_hora <= ?"
                params.append(data_fim + " 23:59:59")
            if epi_filtro:
                sql += " AND epis_ausentes LIKE ?"
                params.append(f"%{epi_filtro}%")
            c.execute(sql, params)
            return c.fetchone()["n"]
        finally:
            conn.close()

    def validar_usuario(self, usuario: str, senha: str):
        senha_hash = hashlib.sha256(senha.encode()).hexdigest()
        conn = _conectar()
        try:
            c = conn.cursor()
            c.execute(
                "SELECT id, nome, usuario FROM usuarios WHERE usuario=? AND senha_hash=? AND ativo=1",
                (usuario, senha_hash)
            )
            row = c.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def estatisticas(self):
        conn = _conectar()
        hoje = datetime.date.today().strftime("%d/%m/%Y")
        try:
            c = conn.cursor()
            stats = {}
            c.execute("SELECT COUNT(*) as n FROM ocorrencias")
            stats["total_ocorrencias"] = c.fetchone()["n"]
            c.execute("SELECT COUNT(*) as n FROM ocorrencias WHERE data_hora LIKE ?", (f"{hoje}%",))
            stats["hoje"] = c.fetchone()["n"]
            c.execute("SELECT COUNT(*) as n FROM ocorrencias WHERE revisado=0")
            stats["nao_revisadas"] = c.fetchone()["n"]
            c.execute("SELECT COUNT(*) as n FROM cameras WHERE ativa=1")
            stats["cameras_ativas"] = c.fetchone()["n"]
            return stats
        finally:
            conn.close()

    def limpar_ocorrencias(self):
        conn = _conectar()
        try:
            conn.execute("DELETE FROM ocorrencias")
            conn.commit()
        finally:
            conn.close()
