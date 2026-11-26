# -*- coding: utf-8 -*-
"""
============================================================================
Importador de Dados Pendentes do Fallback Local para o PostgreSQL (SONAX).

Uso:
    python importar_fallback_bd.py
    python importar_fallback_bd.py --dry-run
    python importar_fallback_bd.py --pasta C:/caminho/com/fallback

O que este script importa de `fallback_bd_pendentes.json` (ou `.csv`):
    1. Cache do robô Google RPA -> `cache_rpa_google`
    2. Transcrição -> `registro_chamadas`
    3. Empresa e Revisão -> `empresa` e `registro_chamadas` (`revisao`, `id_empresa`)
    4. Análise Comercial IA -> 7+ tabelas (`avaliacao_ia`, `avaliacao_sdr`,
       `avaliacao_oportunidade_treinamento`, `avaliacao_criterio`,
       `analise_spin`, `analise_bant`, `interlocutor`, `crm`, `analise_perfil`),
       preservando a data original em que a avaliação foi feita (`data_avaliacao`)
       e a data/hora da chamada (`dt_inicio`).
============================================================================
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.database.db import testar_conexao_bd
from app.services.fallback_bd import (
    carregar_fallback_bd,
    obter_caminhos_fallback,
    reprocessar_fallback_bd,
)


def _resumir_itens(itens: list[dict]) -> None:
    qtd_transc = sum(1 for i in itens if i.get("transcricao"))
    qtd_rpa = sum(
        1
        for i in itens
        if i.get("rpa_telefone")
        and i.get("rpa_texto_google")
        and str(i.get("rpa_texto_google")).strip() != "Não encontrado"
    )
    qtd_rev = sum(1 for i in itens if i.get("revisao"))
    qtd_ana = sum(1 for i in itens if isinstance(i.get("analise_json"), dict) and i.get("analise_json"))

    print(f"Total de chamadas pendentes: {len(itens)}")
    print(f"  • Com transcrição: {qtd_transc}")
    print(f"  • Com dados RPA Google: {qtd_rpa}")
    print(f"  • Com revisão + empresa: {qtd_rev}")
    print(f"  • Com análise comercial IA: {qtd_ana}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Importa os dados salvos em fallback local (JSON/CSV) para o PostgreSQL do SONAX."
    )
    parser.add_argument(
        "--pasta",
        type=Path,
        default=None,
        help="Pasta onde estão `fallback_bd_pendentes.json` e `.csv` (padrão: raiz do projeto).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas exibe o resumo dos registros pendentes sem conectar ou gravar no banco.",
    )
    args = parser.parse_args(argv)

    pasta_raiz = args.pasta.resolve() if args.pasta else None
    caminho_csv, caminho_json = obter_caminhos_fallback(pasta_raiz)

    print("=== SONAX — Importação do Fallback Local para o Banco de Dados ===")
    print(f"JSON: {caminho_json}")
    print(f"CSV : {caminho_csv}")

    itens = carregar_fallback_bd(pasta_raiz)
    if not itens:
        print("\nNenhum registro pendente encontrado para importar.")
        return 0

    print()
    _resumir_itens(itens)

    if args.dry_run:
        print("\n[DRY-RUN] Detalhamento dos registros:")
        for idx, item in enumerate(itens, 1):
            data_av = item.get("data_avaliacao") or (
                (item.get("analise_json") or {}).get("avaliacao_ia", {}).get("data_avaliacao")
                if isinstance(item.get("analise_json"), dict)
                else "-"
            )
            print(
                f"  {idx:02d}. {item.get('log')} | protocolo={item.get('protocolo')} | "
                f"empresa={item.get('empresa_nome') or '-'} | data_avaliacao={data_av or '-'}"
            )
        print("\n[DRY-RUN] Nenhuma alteração foi feita no banco.")
        return 0

    print("\nTestando conexão com o PostgreSQL...")
    bd_ok, motivo = testar_conexao_bd(connect_timeout=5)
    if not bd_ok:
        print(f"[ERRO] Não foi possível conectar ao PostgreSQL: {motivo}")
        print("Seus arquivos de fallback foram preservados sem alterações.")
        return 1

    print("Conexão estabelecida! Iniciando importação...\n")
    resumo = reprocessar_fallback_bd(pasta_raiz=pasta_raiz, verbose=True)

    print("\n=== Resumo da Importação ===")
    print(f"Processados: {resumo['processados']}")
    print(f"Sucesso    : {resumo['sucesso']}")
    print(f"Falha      : {resumo['falha']}")

    if resumo["falha"] > 0:
        print("\n[AVISO] Os registros com falha foram mantidos nos arquivos de fallback com o motivo do erro.")
        return 2

    print("\nTodos os registros pendentes foram importados com sucesso!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
