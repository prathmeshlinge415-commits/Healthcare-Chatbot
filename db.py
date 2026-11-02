"""Database layer: MySQL (default) with an optional SQLite backend used for automated tests/demo.
All SQL in the app uses %s placeholders and portable syntax so it runs on both."""
import re
import sqlite3
import datetime as dt
from pathlib import Path
from flask import g, current_app

SCHEMA_FILE = Path(__file__).parent / "sql" / "schema.sql"

# columns added to the ORIGINAL project's tables when upgrading an existing database
UPGRADE_COLUMNS = {
    "patient": {"date_of_birth": "VARCHAR(10)", "gender": "VARCHAR(20)", "city": "VARCHAR(100)",
                "blood_group": "VARCHAR(5)", "emergency_contact_name": "VARCHAR(120)",
                "emergency_contact_phone": "VARCHAR(20)", "created_at": "DATETIME NULL"},
    "appointments": {"status": "VARCHAR(20) NOT NULL DEFAULT 'confirmed'", "created_at": "DATETIME NULL",
                     "updated_at": "DATETIME NULL"},
}


def _norm(row):
    if row is None:
        return None
    out = {}
    for k, v in row.items():
        if isinstance(v, (dt.datetime, dt.date)):
            v = v.isoformat(sep=" ")[:19] if isinstance(v, dt.datetime) else v.isoformat()
        elif isinstance(v, dt.timedelta):
            s = int(v.total_seconds()); v = f"{s // 3600:02d}:{(s % 3600) // 60:02d}"
        out[k] = v
    return out


class Database:
    def __init__(self, conn, backend):
        self.conn, self.backend = conn, backend

    def _sql(self, sql):
        return sql.replace("%s", "?") if self.backend == "sqlite" else sql

    def _cursor(self):
        return self.conn.cursor() if self.backend == "sqlite" else self.conn.cursor(dictionary=True)

    def all(self, sql, params=()):
        cur = self._cursor()
        try:
            cur.execute(self._sql(sql), tuple(params))
            return [_norm(dict(r)) for r in cur.fetchall()]
        finally:
            cur.close()

    def one(self, sql, params=()):
        rows = self.all(sql, params)
        return rows[0] if rows else None

    def run(self, sql, params=()):
        """Execute a write. Returns (lastrowid, rowcount). Caller commits via db.commit()."""
        cur = self._cursor()
        try:
            cur.execute(self._sql(sql), tuple(params))
            return cur.lastrowid, cur.rowcount
        finally:
            cur.close()

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


def connect(cfg, with_database=True):
    if cfg["DB_BACKEND"] == "sqlite":
        conn = sqlite3.connect(cfg["SQLITE_PATH"])
        conn.row_factory = sqlite3.Row
        return Database(conn, "sqlite")
    import mysql.connector  # imported lazily so SQLite mode needs no MySQL driver
    kw = dict(host=cfg["DB_HOST"], port=cfg["DB_PORT"], user=cfg["DB_USER"], password=cfg["DB_PASSWORD"],
              charset="utf8mb4", connection_timeout=5)
    if with_database:
        kw["database"] = cfg["DB_NAME"]
    return Database(mysql.connector.connect(**kw), "mysql")


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config)
    return g.db


def close_db(_exc=None):
    d = g.pop("db", None)
    if d is not None:
        d.close()


def _statements(backend):
    text = re.sub(r"--[^\n]*", "", SCHEMA_FILE.read_text(encoding="utf-8"))
    for stmt in (s.strip() for s in text.split(";")):
        if not stmt or re.match(r"(CREATE DATABASE|USE)\b", stmt, re.I):
            continue
        if backend == "sqlite":
            stmt = re.sub(r"INT AUTO_INCREMENT PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT", stmt)
        yield stmt


def init_schema(cfg):
    """Create database/tables if missing and add new columns to tables from the original project."""
    if cfg["DB_BACKEND"] == "mysql":
        boot = connect(cfg, with_database=False)
        boot.run(f"CREATE DATABASE IF NOT EXISTS `{cfg['DB_NAME']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        boot.commit(); boot.close()
    d = connect(cfg)
    for stmt in _statements(cfg["DB_BACKEND"]):
        d.run(stmt)
    d.commit()
    for table, cols in UPGRADE_COLUMNS.items():  # upgrade path for databases created by the old version
        if d.backend == "sqlite":
            existing = {r["name"] for r in d.all(f"PRAGMA table_info({table})")}
        else:
            existing = {r["COLUMN_NAME"] for r in d.all(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
                (cfg["DB_NAME"], table))}
        for col, ddl in cols.items():
            if col not in existing:
                d.run(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    d.commit(); d.close()
