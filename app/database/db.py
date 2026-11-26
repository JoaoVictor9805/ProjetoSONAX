# -*- coding: utf-8 -*-
"""
Camada de conexão com o Postgres.
Usa psycopg v3 em modo context manager (transação automática).
"""

import os
from contextlib import contextmanager

import psycopg

from app.database.config import get_database_url


def _obter_connect_timeout() -> int:
    raw = (os.environ.get("DB_CONNECT_TIMEOUT") or "5").strip()
    try:
        val = int(raw)
        return max(1, val)
    except ValueError:
        return 5


@contextmanager
def conectar(connect_timeout: int | None = None):
    """Abre uma conexão e entrega um cursor dentro de transação.

    Uso:
        with conectar() as cur:
            cur.execute("SELECT ...")
    """
    timeout = _obter_connect_timeout() if connect_timeout is None else max(1, int(connect_timeout))
    conn = psycopg.connect(get_database_url(), connect_timeout=timeout)
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def testar_conexao_bd(connect_timeout: int = 3) -> tuple[bool, str | None]:
    """Testa rapidamente se a configuração e a conexão com o PostgreSQL estão disponíveis."""
    try:
        url = get_database_url()
    except KeyError as exc:
        return False, f"Variável ausente no .env: {exc}"

    try:
        conn = psycopg.connect(url, connect_timeout=max(1, int(connect_timeout)))
        conn.close()
        return True, None
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
