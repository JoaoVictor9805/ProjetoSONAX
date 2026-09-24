# -*- coding: utf-8 -*-
"""
Leitura das configurações de conexão a partir de variáveis de ambiente
(arquivo .env na raiz do projeto).

Uso:
    from app.database.config import get_database_url
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv


def carregar_env() -> Path | None:
    """Carrega o arquivo .env respeitando a seguinte ordem de prioridade:
    1. Arquivo .env externo ao lado do executável (.exe)
    2. Arquivo .env embutido no pacote do PyInstaller (_MEIPASS)
    3. Arquivo .env na raiz do projeto (modo desenvolvimento)
    """
    if getattr(sys, "frozen", False):
        # 1. Checa se existe .env externo ao lado do .exe (Prioridade Máxima)
        pasta_exe = Path(sys.executable).resolve().parent
        env_externo = pasta_exe / ".env"
        if env_externo.is_file():
            load_dotenv(env_externo, override=True)
            return env_externo

        # 2. Fallback: .env embutido pelo PyInstaller no diretório temporário
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            env_interno = Path(meipass) / ".env"
            if env_interno.is_file():
                load_dotenv(env_interno, override=True)
                return env_interno
        return None
    else:
        # 3. Modo desenvolvimento (.py)
        raiz = Path(__file__).resolve().parents[2]
        env_dev = raiz / ".env"
        if env_dev.is_file():
            load_dotenv(env_dev, override=True)
            return env_dev
        return None


# Carrega o .env na inicialização do módulo
_ENV_CARREGADO = carregar_env()


def get_database_url() -> str:
    """Monta a URL de conexão ao Postgres a partir de variáveis isoladas."""
    user = os.environ["DB_USER"]
    password = os.environ["DB_PASSWORD"]
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    dbname = os.environ["DB_NAME"]
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
