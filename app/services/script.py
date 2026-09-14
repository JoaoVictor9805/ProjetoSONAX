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

from aiohttp import resolver
from typing_extensions import Tuple
from aiohttp import log
from app.services.analise_final_AI import analisar_ligacao
from app.services.chamadas_dao import buscar_revisao
from app.services.revisao import revisar_texto
from app.services.qualidade_audio import analisar_audio
from app.services.qualidade_audio import classificar_qualidade_audio
from app.services.qualidade_audio import classificar_qualidade_transcricao
from app.services.qualidade_audio import avaliar_qualidade_transcricao
from app.services.qualidade_audio import calcular_metricas_whisper
from app.services.qualidade_audio import analisar_transcricao
from app.services.planilha import exportar_transcricao_para_planilha
from app.services import transcrever
import shutil                # biblioteca para copiar os arquivos de um lugar para outro.
import struct                # Biblioteca para ler e interpretar dados binários puros (necessário para ler o cabeçalho do arquivo WAV).
import threading             # usado apenas para anotação de tipo (cancel: threading.Event | None)
from pathlib import Path     # Facilita muito a manipulação de caminhos de arquivos e pastas
from typing import Callable   # usado apenas para anotação de tipo (on_progress)
from datetime import datetime

from app.database.db import conectar
from app.services.chamadas_dao import (
    buscar_nome_atendente,
    inserir_registro_chamada,
    registro_ja_existe,
    buscar_transcricao,
    verificar_coluna_revisao,
    inserir_revisao,
    verificar_coluna_analise,
    inserir_analise
)
from app.services.parses import (
    parse_data,
    parse_nome_arquivo,
    parse_hora
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


def classificar_wavs(wavs: list, cancel: threading.Event | None = None) -> tuple:
    """Separa a lista de WAVs em (>1min, <=1min, inválidos)."""
    longos, curtos, invalidos = [], [], []
    for w in wavs:
        if cancel is not None and cancel.is_set():
            break
        d = duracao_wav(w)
        if d is None:
            invalidos.append(w)
        elif d > 60:
            longos.append((w, d))
        else:
            curtos.append((w, d))
    return longos, curtos, invalidos


def filtrar_por_qualidade_audio(
    longos: list,
    cancel: threading.Event | None = None,
    modo_dev: threading.Event | None = None,
) -> tuple[list, list]:
    """Analisa a qualidade de áudio dos WAVs longos e remove os 'Péssimos'.

    Retorna (longos_filtrados, rejeitados) onde:
    - longos_filtrados : lista de (Path, duracao) aprovados.
    - rejeitados       : lista de Path reprovados (só o caminho, sem duração).

    `modo_dev` (opcional): quando setado, os rótulos exibidos são os nomes
    reais dos arquivos em vez de "Audio NN".
    """
    filtrados = []
    rejeitados = []
    for idx, (caminho, duracao) in enumerate(longos, 1):
        if modo_dev is not None and modo_dev.is_set():
            rotulo_audio = caminho.name
        else:
            rotulo_audio = f"Audio {idx:02d}"
        if cancel is not None and cancel.is_set():
            break
        try:
            dados = analisar_audio(caminho)
            classificacao = classificar_qualidade_audio(dados)
        except Exception as e :
            # Se a análise falhar, mantém o áudio (não penaliza por erro técnico)
            print(f"  [qualidade] erro ao analisar {rotulo_audio}: {e} — mantido por padrão")
            filtrados.append((caminho, duracao))
            continue

        if classificacao == "Péssimo":
            print(f"  [qualidade] {rotulo_audio} reprovado ({classificacao}) — excluído do processamento")
            rejeitados.append(caminho)
        else:
            print(f"  [qualidade] {rotulo_audio} aprovado ({classificacao})")
            filtrados.append((caminho, duracao))

    return filtrados, rejeitados


def copiar_longos_para_pasta(
    longos: list,
    pasta_destino: Path,
    cancel: threading.Event | None = None,
    on_progress: "Callable[[int, int, Path], None] | None" = None,
) -> list:
    """Copia os áudios >1min para a pasta destino. Retorna a lista de copiados
    [(path_destino, duracao_seg)] — usada depois pelo salvamento no banco."""
    pasta_destino.mkdir(exist_ok=True)
    copiados = []
    vistos = set()
    total_longos = len(longos)
    for caminho, d in sorted(longos, key=lambda x: -x[1]):
        if cancel is not None and cancel.is_set():
            break
        if caminho.name in vistos:
            continue
        vistos.add(caminho.name)
        destino = pasta_destino / caminho.name
        shutil.copy2(caminho, destino)
        copiados.append((destino, d))
        if on_progress is not None:
            try:
                on_progress(len(copiados), total_longos, caminho)
            except Exception:
                pass
    return copiados


def _notificar_progresso(
    callback: Callable | None,
    i: int,
    total: int,
    caminho: Path,
    frac: float,
    msg: str,
) -> None:
    """Auxiliar para notificar progresso suportando múltiplas assinaturas."""
    if callback is None:
        return
    try:
        callback(i, total, caminho, frac, msg)
    except TypeError:
        try:
            callback(i, total, caminho)
        except Exception:
            pass
    except Exception:
        pass


def salvar_no_banco(
    copiados: list,
    cancel: "threading.Event | None" = None,
    on_progress: "Callable | None" = None,
    modo_dev: "threading.Event | None" = None,
) -> tuple[int, int]:
    """Para cada arquivo copiado: transcreve, parseia o nome, busca o
    atendente pelo ramal e insere UM único registro em registro_chamadas
    com a transcrição já preenchida.

    Retorna uma tupla (inseridos, ja_existentes). Pula (com aviso) se o registro
    já existir no banco, se ramal não existir em `origem` ou se algum campo
    essencial estiver ausente.

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
    ja_existentes = 0
    total = len(copiados)
    for i, (caminho, _) in enumerate(copiados, start=1):
        if modo_dev is not None and modo_dev.is_set():
            rotulo_audio = caminho.name
        else:
            rotulo_audio = f"Audio {i:02d}"
        if cancel is not None and cancel.is_set():
            print(f"  [cancelado] parando antes de {rotulo_audio} ({caminho.name}) "
                  f"após {inseridos} registro(s) inserido(s).")
            return inseridos, ja_existentes

        # --- Verificação antecipada no banco antes de transcrever ---
        with conectar() as cur:
            if registro_ja_existe(cur, caminho.name):
                ja_existentes += 1
                print(f"  [aviso] {rotulo_audio} já registrado no banco — pulando.")
                _notificar_progresso(
                    on_progress,
                    i,
                    total,
                    caminho,
                    1.0,
                    f"[{i}/{total}] {rotulo_audio} já existe no banco (pulado)",
                )
                continue

        # 1) Transcrição com progresso contínuo
        _notificar_progresso(
            on_progress,
            i,
            total,
            caminho,
            0.0,
            f"[{i}/{total}] Iniciando transcrição de: {rotulo_audio}",
        )
        print(f"  [whisper] [{i}/{total}] transcrevendo: {rotulo_audio} ...")

        def _on_sub_progress(sub_frac: float) -> None:
            pct = int(sub_frac * 100)
            _notificar_progresso(
                on_progress,
                i,
                total,
                caminho,
                sub_frac * 0.85,
                f"[{i}/{total}] {rotulo_audio}: {pct}% transcrevendo...",
            )

        try:
            texto, metricas_whisper = transcrever_arquivo(
                caminho,
                cancel=cancel,
                on_progress=_on_sub_progress,
            )
        except TranscricaoCancelada as e:
            print(f"  [cancelado] {e} — nada de "
                  f"{rotulo_audio} foi inserido.")
            return inseridos, ja_existentes

        _notificar_progresso(
            on_progress,
            i,
            total,
            caminho,
            0.90,
            f"[{i}/{total}] {rotulo_audio}: transcrição concluída. Gravando no banco...",
        )

        dados_transcricao = analisar_transcricao(texto)
        dados_whisper = calcular_metricas_whisper(metricas_whisper)

        dados = {
            **dados_transcricao,
            **dados_whisper
        }

        avaliacao = avaliar_qualidade_transcricao(dados)
        qualidade = avaliacao["classificacao"]

        # Exporta transcrição com todos os critérios de qualidade e métricas para a planilha
        status_fluxo = "Descartado (qualidade péssima)" if qualidade == "Péssimo" else "Aprovado para banco"
        try:
            exportar_transcricao_para_planilha(
                caminho_audio=caminho,
                texto_transcricao=texto,
                dados_avaliacao={
                    **dados,
                    **avaliacao,
                    "status_fluxo": status_fluxo,
                },
            )
        except Exception as e:
            print(f"  [aviso planilha] Falha ao registrar na planilha {rotulo_audio}: {e}")

        if qualidade == "Péssimo":
            print(f"  [aviso] transcrição de {rotulo_audio} não é adequada ({avaliacao['pontuacao']}/100 - {avaliacao['motivo']}) — pulando")
            continue

        # 2) INSERT em uma transação pequena e isolada
        info = parse_nome_arquivo(caminho)

        if not info["ramal"].isdigit():
            print(f"  [aviso] ramal inválido em {rotulo_audio}: "
                  f"{info['ramal']!r} — pulando")
            continue

        data = parse_data(info["data"])
        if data is None:
            print(f"  [aviso] data inválida em {rotulo_audio}: "
                  f"{info['data']!r} — pulando")
            continue

        hora = parse_hora(info["hora"])
        if hora is None:
            print(f"  [aviso] hora inválida em {rotulo_audio}: "
                  f"{info['hora']!r} — pulando")
            continue

        data_ligacao = datetime.combine(data, hora) if hora else datetime(data.year, data.month, data.day)

        ramal = int(info["ramal"])
        with conectar() as cur:
            nome = buscar_nome_atendente(cur, ramal, data_ligacao)
            if nome is None:
                print(f"  [aviso] ramal {ramal} não encontrado em `origem` "
                  f"({rotulo_audio}) — pulando")
                continue

            id_reg = inserir_registro_chamada(
                cur,
                ramal=ramal,
                agente_nome=nome,
                data_ligacao=data_ligacao,
                log_arquivo=caminho.name,
                transcricao=texto,
            )
        preview = texto[:60].replace("\n", " ")
        print(f"  [bd] registro #{id_reg} inserido: "
              f"ramal={ramal} ({nome})  data={data}  "
              f"-> {rotulo_audio}  (\"{preview}...\")")
        inseridos += 1
        _notificar_progresso(
            on_progress,
            i,
            total,
            caminho,
            1.0,
            f"[{i}/{total}] {rotulo_audio} gravado com sucesso no banco!",
        )

    return inseridos, ja_existentes

def gerar_revisao_transcricao(log: str, rotulo_audio: str | None = None, cancel: threading.Event | None = None, ) -> str | None:
    """Gere a revisão a partir da coluna de transcrição, utilizando um modelo de IA"""
    nome_exibicao = rotulo_audio or log

    if cancel is not None and cancel.is_set():
            print(f"  [cancelado] revisão de {nome_exibicao} não iniciada.")
            return None

    with conectar() as cur:
        if verificar_coluna_revisao(cur, log):
            print(f"  [revisão] {nome_exibicao} já existe no banco (pulado)")
            return None
        transcricao = buscar_transcricao(cur, log)

    if cancel is not None and cancel.is_set():
        print(f"  [cancelado] revisão de {nome_exibicao} abortada antes da chamada de IA.")
        return None
    
    if not transcricao or not transcricao.strip():
        return None

    try:
        revisao = revisar_texto(transcricao)
    except Exception as e:
        print(f"  [revisão] Falha ao revisar transcrição de {nome_exibicao}: {e}")
        return None

    with conectar() as cur:
        return inserir_revisao(cur, log, revisao)
        
def gerar_analise_revisao(log: str, rotulo_audio: str | None = None, cancel: threading.Event | None = None,) -> Tuple | None:
    """Gera análise de IA a partir da revisão da transcrição dos áudios"""
    with conectar() as cur:

        nome_exibicao = rotulo_audio or log

        if cancel is not None and cancel.is_set():
            print(f"  [cancelado] análise de {nome_exibicao} não iniciada.")
            return None
        if verificar_coluna_revisao(cur, log):
            revisao = buscar_revisao(cur, log)

            if revisao is None:
                print(f"  [análise] {nome_exibicao} não possui revisão de transcrição para analisar (pulado)")

                return None

            # Função para verificar presença no banco
            if verificar_coluna_analise(cur, log):
                print(f"  [análise] {nome_exibicao} já existe no banco (pulado)")
                return None
            try:
                analise_IA = analisar_ligacao(revisao)

                nota = analise_IA["nota"]
                resumo = analise_IA["resumo"]

            except Exception as e:
                nome_exibicao = rotulo_audio or log
                print(f"  [Análise Final] Falha ao realizar análise final da ligação {nome_exibicao}: {e}")
                return None

            with conectar() as cur:
                return inserir_analise(cur, log, nota, resumo)

        else:
            return None

def deletar_pasta(pasta_destino: Path, cancel: threading.Event | None = None) -> None:
    """Deleta a pasta de destino especificada e todo o seu conteúdo recursivamente."""
    if not pasta_destino.exists():
        return

    try:
        shutil.rmtree(pasta_destino, ignore_errors=True)
        print(f"[deletado] pasta {pasta_destino} deletada com sucesso")
    except Exception as e:
        print(f"[aviso] erro ao deletar pasta {pasta_destino}: {e}")