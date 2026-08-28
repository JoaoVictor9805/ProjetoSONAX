# -*- coding: utf-8 -*-
"""
Camada de conexão com o Postgres.
Usa psycopg v3 em modo context manager (transação automática).
"""

from contextlib import contextmanager

import psycopg

from services.config import get_database_url


@contextmanager
def conectar():
    """Abre uma conexão e entrega um cursor dentro de transação.

    Uso:
        with conectar() as cur:
            cur.execute("SELECT ...")
    """
    conn = psycopg.connect(get_database_url())
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
