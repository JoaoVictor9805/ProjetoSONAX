# -*- coding: utf-8 -*-
"""
============================================================================
Biblioteca de domínio: leitura de WAV, parsing de nome, classificação,
cópia, transcrição e persistência no banco de dados.

Este módulo NÃO é executável — ele é importado por `app.main` (ou outros
pontos de entrada). Toda a lógica de CLI (sys.argv, prints de UI,
validação de diretório, retorno de códigos) vive em `app.main`.
============================================================================

USO:
    from app.services.script import (
        classificar_wavs, copiar_longos_para_pasta,
        parse_nome_arquivo, salvar_no_banco, duracao_wav,
    )

==============================================================================
DEFINIÇÃO DAS VARIÁVEIS E ESTRUTURA DO ARQUIVO WAV
==============================================================================

-- VARIÁVEIS DO CABEÇALHO PRINCIPAL (Lidas no começo do arquivo) --
riff : Lê os primeiros 4 bytes. Deve ser b"RIFF" (Resource Interchange File Format).
      Significa que o arquivo é um "contêiner" padrão da Microsoft/IBM.

 _    : O "underline" é usado no Python para descartar um valor. Aqui ele
        ignora o tamanho total do arquivo (que vem logo após o RIFF), pois não usaremos.

wave : Lê mais 4 bytes. Deve ser b"WAVE". É a etiqueta que garante que
       os dados dentro desse contêiner RIFF são um áudio sem compressão.

-- VARIÁVEIS DE NAVEGAÇÃO (Usadas no loop while para explorar o arquivo) --

- O formato WAV é dividido em blocos de informação chamados "chunks".
- cabecalho  : header. Lê os 8 primeiros bytes de cada chunk.
- chunk_id  : "Chunk ID" (Identificador). Lê as 4 letras do 'cabecalho'. É o NOME do bloco (ex: b"fmt ", b"data").
- chunk_size  : "Chunk Size" (Tamanho). Lê os 4 números do 'cabecalho'. É o TAMANHO daquele bloco em bytes.

-- VARIÁVEIS DE CONFIGURAÇÃO E ÁUDIO --

- fmt       : Recebe o conteúdo bruto do bloco b"fmt ". É o "manual de instruções"
             do áudio (ex: se é estéreo, qualidade).
- byte_rate : É a "Taxa de Bytes". Extraído do 'fmt', indica quantos bytes o
            computador precisa ler por 1 segundo de áudio para a música tocar normal.
- data_size : Quando o cid é b"data" (onde está a música em si), o csz é salvo aqui.
            Representa o peso em bytes apenas do som, sem os cabeçalhos.

O tempo final em segundos é simplesmente: data_size / byte_rate
==============================================================================
    """

import shutil                # biblioteca para copiar os arquivos de um lugar para outro.
import struct                # Biblioteca para ler e interpretar dados binários puros (necessário para ler o cabeçalho do arquivo WAV).
import threading             # usado apenas para anotação de tipo (cancel: threading.Event | None)
from pathlib import Path     # Facilita muito a manipulação de caminhos de arquivos e pastas
from typing import Callable   # usado apenas para anotação de tipo (on_progress)

from app.database.db import conectar
from app.services.chamadas_dao import (
    buscar_nome_atendente,
    inserir_registro_chamada,
)
from app.services.parses import (
    parse_data,
    parse_nome_arquivo,
)
from app.services.transcrever import TranscricaoCancelada, transcrever_arquivo


def duracao_wav(caminho: Path):
    """Retorna a duração em segundos do WAV ou None se for inválido."""
    try:
        with open(caminho, "rb") as f:
            riff, _, wave = struct.unpack("<4sI4s", f.read(12))
            if riff != b"RIFF" or wave != b"WAVE":
                return None

            byte_rate = data_size = None

            while True:
                cabecalho = f.read(8)
                if len(cabecalho) < 8:
                    break
                chunk_id, chunk_size = struct.unpack("<4sI", cabecalho)
                if chunk_id == b"fmt ":
                    fmt = f.read(chunk_size)
                    if len(fmt) < 16:
                        return None
                    byte_rate = struct.unpack("<I", fmt[8:12])[0]
                elif chunk_id == b"data":
                    data_size = chunk_size
                    f.seek(chunk_size, 1)
                else:
                    f.seek(chunk_size, 1)
                if chunk_size % 2:
                    f.read(1)
                if byte_rate and data_size is not None:
                    break
        return data_size / byte_rate if byte_rate and data_size else None

    except Exception:
        return None


def classificar_wavs(wavs: list) -> tuple:
    """Separa a lista de WAVs em (>1min, <=1min, inválidos)."""
    longos, curtos, invalidos = [], [], []
    for w in wavs:
        d = duracao_wav(w)
        if d is None:
            invalidos.append(w)
        elif d > 600:
            longos.append((w, d))
        else:
            curtos.append((w, d))
    return longos, curtos, invalidos


def copiar_longos_para_pasta(longos: list, pasta_destino: Path) -> list:
    """Copia os áudios >1min para a pasta destino. Retorna a lista de copiados
    [(path_destino, duracao_seg)] — usada depois pelo salvamento no banco."""
    pasta_destino.mkdir(exist_ok=True)
    copiados = []
    for caminho, d in sorted(longos, key=lambda x: -x[1]):
        destino = pasta_destino / caminho.name
        shutil.copy2(caminho, destino)
        print(f"  {caminho.name:<40} {d:>8.2f} s  "
              f"({d/60:.2f} min)  -> copiado")
        copiados.append((destino, d))
    return copiados


def salvar_no_banco(
    copiados: list,
    cancel: "threading.Event | None" = None,
    on_progress: "Callable[[int, int, Path], None] | None" = None,
) -> int:
    """Para cada arquivo copiado: transcreve, parseia o nome, busca o
    atendente pelo ramal e insere UM único registro em registro_chamadas
    com a transcrição já preenchida.

    Retorna a quantidade inserida. Pula (com aviso) se ramal não existir
    em `origem` ou se algum campo essencial estiver ausente.

    **Cancelamento**: o `cancel` é checado em dois pontos:
      1. **Intra-arquivo** (durante a transcrição do arquivo N) — via
         hook no `tqdm.update` em `transcrever_arquivo`. Se ativado,
         uma `TranscricaoCancelada` sobe; capturamos aqui, logamos, e
         saímos do loop **sem inserir** nada daquele arquivo (o texto
         acumulado foi descartado pelo próprio Whisper).
      2. **Entre arquivos** — checagem explícita antes da próxima
         iteração do loop (cobre o caso do cancel chegar entre o fim
         de uma transcrição e o INSERT, ou entre dois INSERTs).

    O que já foi transcrito+inserido permanece (cada INSERT faz
    `commit` no `with` do `conectar()`).
    """
    inseridos = 0
    total = len(copiados)
    for i, (caminho, _) in enumerate(copiados, start=1):
        if cancel is not None and cancel.is_set():
            print(f"  [cancelado] parando antes de {caminho.name} "
                  f"após {inseridos} registro(s) inserido(s).")
            return inseridos
        if on_progress is not None:
            on_progress(i, total, caminho)

        # 1) Transcrição (pode levantar TranscricaoCancelada se o
        #    usuário cancelar no meio do arquivo atual).
        print(f"  [whisper] transcrevendo: {caminho.name} ...")
        try:
            texto = transcrever_arquivo(caminho, cancel=cancel)
        except TranscricaoCancelada as e:
            print(f"  [cancelado] {e} — nada de "
                  f"{caminho.name} foi inserido.")
            return inseridos

        # 2) INSERT em uma transação pequena e isolada: se o próximo
        #    arquivo for cancelado, este INSERT já está commitado.
        info = parse_nome_arquivo(caminho)

        if not info["ramal"].isdigit():
            print(f"  [aviso] ramal inválido em {caminho.name}: "
                  f"{info['ramal']!r} — pulando")
            continue

        data = parse_data(info["data"])
        if data is None:
            print(f"  [aviso] data inválida em {caminho.name}: "
                  f"{info['data']!r} — pulando")
            continue

        ramal = int(info["ramal"])
        with conectar() as cur:
            nome = buscar_nome_atendente(cur, ramal)
            if nome is None:
                print(f"  [aviso] ramal {ramal} não encontrado em `origem` "
                      f"({caminho.name}) — pulando")
                continue

            id_reg = inserir_registro_chamada(
                cur,
                ramal=ramal,
                nome_atendente=nome,
                data_ligacao=data,
                log_arquivo=caminho.name,
                transcricao=texto,
            )
        preview = texto[:60].replace("\n", " ")
        print(f"  [bd] registro #{id_reg} inserido: "
              f"ramal={ramal} ({nome})  data={data}  "
              f"-> {caminho.name}  (\"{preview}...\")")
        inseridos += 1

    return inseridos
