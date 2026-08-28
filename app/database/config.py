# -*- coding: utf-8 -*-
"""
Leitura das configurações de conexão a partir de variáveis de ambiente
(arquivo .env na raiz do projeto).

Uso:
    from app.database.config import get_database_url
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega o .env da raiz do projeto (dois níveis acima de app/database/).
_RAIZ = Path(__file__).resolve().parents[2]
load_dotenv(_RAIZ / ".env")


def get_database_url() -> str:
    """Monta a URL de conexão ao Postgres a partir de variáveis isoladas."""
    user = os.environ["DB_USER"]
    password = os.environ["DB_PASSWORD"]
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    dbname = os.environ["DB_NAME"]
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
