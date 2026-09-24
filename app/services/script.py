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

from app.services.analise_final_AI import analisar_ligacao
from app.services.chamadas_dao import buscar_revisao
from app.services.revisao import revisar_texto
from app.services.qualidade_audio import (
    analisar_audio,
    classificar_qualidade_audio,
    avaliar_qualidade_transcricao,
    analisar_transcricao,
)
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
    verificar_tabela_analise,
    inserir_analise,
)
from app.services.parses import (
    parse_data,
    parse_nome_arquivo,
    parse_hora,
)
from app.services.assemblyai_transcribe import (
    transcrever_audio_assemblyai,
    TranscricaoCancelada,
)
from app.logs import log_dev_exc



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
    on_progress: "Callable[[int, int, Path], None] | None" = None,
) -> tuple[list, list]:
    """Analisa a qualidade de áudio dos WAVs longos e remove os 'Péssimos'.

    Retorna (longos_filtrados, rejeitados) onde:
    - longos_filtrados : lista de (Path, duracao) aprovados.
    - rejeitados       : lista de Path reprovados (só o caminho, sem duração).

    `modo_dev` (opcional): mantido por compatibilidade de assinatura, mas
    não é mais usado para decidir o rótulo — o rótulo impresso aqui é
    sempre genérico ("Audio NN"); a troca para o nome real no Log Dev é
    feita por `app.py` a partir do `path` associado aos eventos de
    progresso, nunca a partir do texto congelado nos `print()`.

    `on_progress` (opcional): chamado a cada arquivo, ANTES do print,
    como `on_progress(idx, total, caminho)` — mesmo padrão de
    `copiar_longos_para_pasta`. É assim que `worker.py` ensina o mapa
    "Audio NN" → nome real para esta etapa, já que ela só usa `print()`
    (sem `ProgressEvent`/`path` próprio).
    """
    filtrados = []
    rejeitados = []
    total_longos = len(longos)
    for idx, (caminho, duracao) in enumerate(longos, 1):
        classificacao = None

        # Rótulo sempre genérico — a troca para o nome real (Log Dev)
        # é responsabilidade exclusiva de app.py._formatar_linha.
        rotulo_audio = f"Audio {idx:02d}"

        if on_progress is not None:
            try:
                on_progress(idx, total_longos, caminho)
            except Exception:
                pass

        if cancel is not None and cancel.is_set():
            break
        for tentativa in range(1, 4):
            try:
                dados = analisar_audio(caminho)
                classificacao = classificar_qualidade_audio(dados)
                break

            except Exception as e :
                print(
                        f"[AVISO] Não foi possível analisar a qualidade "
                        f"de '{rotulo_audio}' "
                        f"(tentativa {tentativa}/3)"
                    )
                log_dev_exc()
                if tentativa < 3:
                    print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")
                continue
                
        else:
            print(
                f"[ERRO] Não foi possível analisar a qualidade "
                f"de '{rotulo_audio}' após 3 tentativas — "
                f"excluído do processamento."
            )
            rejeitados.append(caminho)
            continue

        if classificacao == "Péssimo":
            print(f"  [INFO] {rotulo_audio} reprovado ({classificacao}) — excluído do processamento")
            rejeitados.append(caminho)
        else:
            print(f"  [INFO] {rotulo_audio} aprovado ({classificacao})")
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
        for tentativa in range(1,4):
            try:
                shutil.copy2(caminho, destino)
                break
            except Exception as e:
                print(
                   f"  [AVISO] Falha ao copiar '{caminho.name}' "
                   f"(tentativa {tentativa}/3)"
                )
                log_dev_exc()
                if tentativa < 3:
                    print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")
        
        else:
           print(f"  [ERRO] Não foi possível copiar '{caminho.name}' após 3 tentativas.")
           continue
           
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
) -> tuple[int, int, dict[str, dict]]:
    """Para cada arquivo copiado: transcreve, parseia o nome, busca o
    atendente pelo ramal e insere UM único registro em registro_chamadas
    com a transcrição já preenchida.

    Retorna uma tupla (inseridos, ja_existentes, mapa_diarizacao). Pula (com aviso) se o registro
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
    mapa_diarizacao: dict[str, dict] = {}
    total = len(copiados)
    for i, (caminho, _) in enumerate(copiados, start=1):
        # Rótulo sempre genérico — a troca para o nome real (Log Dev)
        # é responsabilidade exclusiva de app.py._formatar_linha.
        rotulo_audio = f"Audio {i:02d}"
        if cancel is not None and cancel.is_set():
            print(f"  [CANCELADO] Parando antes de {rotulo_audio}, "
                  f"após {inseridos} registro(s) inserido(s).")
            return inseridos, ja_existentes, mapa_diarizacao

        # --- Verificação antecipada no banco antes de transcrever ---
        try:
            with conectar() as cur:
                if registro_ja_existe(cur, caminho.name):
                    ja_existentes += 1
                    _notificar_progresso(
                        on_progress,
                        i,
                        total,
                        caminho,
                        1.0,
                        f"[AVISO] [{i}/{total}] {rotulo_audio} - Transcrição já registrada no banco (pulado)",
                    )
                    continue

        except Exception as e:
            print(
                f"  [ERRO] Falha ao verificar se '{rotulo_audio}' "
                f"já existe no banco"
            )
            log_dev_exc()
            continue

        # 1) Transcrição e Diarização via AssemblyAI (Universal-3.5 Pro)
        _notificar_progresso(
            on_progress,
            i,
            total,
            caminho,
            0.0,
            f"[INFO] [{i}/{total}] Enviando {rotulo_audio} para AssemblyAI (Universal-3.5 Pro)...",
        )
        print(f"  [INFO] [{i}/{total}] Transcrevendo e diarizando (AssemblyAI): {rotulo_audio} ...")

        def _on_sub_progress(sub_frac: float, msg: str = "") -> None:
            pct = int(sub_frac * 100)
            _notificar_progresso(
                on_progress,
                i,
                total,
                caminho,
                sub_frac * 0.85,
                f"[INFO] [{i}/{total}] {rotulo_audio}: {pct}% {msg or 'AssemblyAI processando...'}",
            )

        res_assembly = None
        for tentativa in range(1, 4):
            try:
                res_assembly = transcrever_audio_assemblyai(
                    caminho,
                    cancel=cancel,
                    on_progress=_on_sub_progress,
                    speakers_expected=3,
                )
                break

            except TranscricaoCancelada:
                return inseridos, ja_existentes, mapa_diarizacao

            except Exception as e:
                print(
                    f"[AVISO] Falha na transcrição AssemblyAI de '{rotulo_audio}' "
                    f"(tentativa {tentativa}/3)"
                )
                log_dev_exc()
                if tentativa < 3:
                    print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")

        else:
            print(
                f"[ERRO] Não foi possível transcrever "
                f"'{rotulo_audio}' via AssemblyAI após 3 tentativas. Arquivo ignorado."
            )
            continue

        texto_formatado = res_assembly["texto_formatado"]
        texto_diarizado = texto_formatado
        texto_puro = res_assembly.get("texto", texto_formatado)

        # 2) Avaliação de qualidade da transcrição
        try:
            dados_transcricao = analisar_transcricao(texto_puro)
            metricas_assembly = res_assembly.get("metricas", {})

            dados = {
                **dados_transcricao,
                **metricas_assembly,
            }

            avaliacao = avaliar_qualidade_transcricao(dados)

        except Exception as e:
            print(
                f"  [ERRO] Falha ao avaliar a transcrição "
                f"de '{rotulo_audio}'"
            )
            log_dev_exc()
            continue

        qualidade = avaliacao["classificacao"]

        if qualidade == "Péssimo":
            print(f"  [AVISO] Transcrição de {rotulo_audio} não é adequada ({avaliacao['pontuacao']}/100 - {avaliacao['motivo']}) — pulando")
            continue

        _notificar_progresso(
            on_progress,
            i,
            total,
            caminho,
            0.90,
            f"[INFO] [{i}/{total}] {rotulo_audio}: transcrição e diarização concluídas. Gravando no banco...",
        )

        # 3) INSERT em uma transação pequena e isolada
        try:
            info = parse_nome_arquivo(caminho)
        except Exception as e:
            print(
                f"  [ERRO] Falha ao interpretar o nome do arquivo "
                f"'{rotulo_audio}'"
            )
            log_dev_exc()
            continue

        if not info["ramal"].isdigit():
            print(f"  [AVISO] Ramal inválido em {rotulo_audio}: "
                  f"{info['ramal']!r} — pulando")
            continue

        data = parse_data(info["data"])
        if data is None:
            print(f"  [AVISO] Data inválida em {rotulo_audio}: "
                  f"{info['data']!r} — pulando")
            continue

        hora = parse_hora(info["hora"])
        if hora is None:
            print(f"  [AVISO] Hora inválida em {rotulo_audio}: "
                  f"{info['hora']!r} — pulando")
            continue

        data_ligacao = datetime.combine(data, hora) if hora else datetime(data.year, data.month, data.day)

        ramal = int(info["ramal"])
        
        id_reg = None
        nome = None

        for tentativa in range(1, 4):
            try:
                with conectar() as cur:
                    nome = buscar_nome_atendente(
                        cur,
                        ramal,
                        data_ligacao,
                    )

                    if nome is None:
                        print(
                            f"  [AVISO] ramal {ramal} não encontrado em `origem` "
                            f"({rotulo_audio}) — pulando"
                        )
                        break

                    id_reg = inserir_registro_chamada(
                        cur,
                        ramal=ramal,
                        agente_nome=nome,
                        data_ligacao=data_ligacao,
                        log_arquivo=caminho.name,
                        transcricao=texto_formatado,
                    )

                break

            except Exception as e:
                print(
                    f"  [ERRO] Falha ao salvar '{rotulo_audio}' "
                    f"no banco de dados "
                    f"(tentativa {tentativa}/3)"
                )
                log_dev_exc()
                if tentativa < 3:
                    print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")

        else:
            print(
                f"  [ERRO] Não foi possível inserir "
                f"'{rotulo_audio}' após 3 tentativas."
            )
            continue

        if nome is None:
            continue

        if id_reg is None:
            print(
                f"  [AVISO] Transcrição de '{rotulo_audio}' já existe no banco — pulando"
            )
            ja_existentes += 1
            continue

        # Guarda o diálogo diarizado e o atendente em memória para a fase de revisão
        mapa_diarizacao[caminho.name] = {
            "texto_diarizado": texto_diarizado,
            "agente_nome": nome,
        }

        inseridos += 1
        _notificar_progresso(
            on_progress,
            i,
            total,
            caminho,
            1.0,
            f"[INFO] [{i}/{total}] {rotulo_audio} gravado com sucesso no banco!",
        )

    return inseridos, ja_existentes, mapa_diarizacao

def gerar_revisao_transcricao(
    log: str,
    texto_diarizado: str | None = None,
    agente_nome: str | None = None,
    rotulo_audio: str | None = None,
    cancel: threading.Event | None = None,
) -> str | None:
    """Gere a revisão a partir do diálogo diarizado e dados do atendente, utilizando modelo de IA."""
    nome_exibicao = rotulo_audio or log

    if cancel is not None and cancel.is_set():
        print(f"  [CANCELADO] Revisão de {nome_exibicao} não iniciada.")
        return None

    try:
        with conectar() as cur:
            if verificar_coluna_revisao(cur, log):
                print(f"  [AVISO] Revisão de {nome_exibicao} já existe no banco (pulado)")
                return None
            
            # Se não foi fornecido em memória, busca a transcrição padrão do banco
            if not texto_diarizado or not texto_diarizado.strip():
                texto_diarizado = buscar_transcricao(cur, log)

    except Exception as e:
        print(
            f"  [ERRO] Falha ao verificar revisão de '{rotulo_audio}' no banco"
        )
        log_dev_exc()
        return None

    if cancel is not None and cancel.is_set():
        print(f"  [CANCELADO] Revisão de {nome_exibicao} abortada antes da chamada de IA.")
        return None
    
    if not texto_diarizado or not texto_diarizado.strip():
        return None

    revisao = None

    for tentativa in range(1, 4):
        try:
            revisao = revisar_texto(texto_diarizado, nome_atendente=agente_nome)
            break
        except Exception as e:
            print(
                f"  [ERRO] Falha ao revisar transcrição "
                f"de {nome_exibicao} "
                f"(tentativa {tentativa}/3)"
            )
            log_dev_exc()
            if tentativa < 3:
                print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")
        
    else:
        print(
            f"  [ERRO] Não foi possível revisar "
            f"{nome_exibicao} após 3 tentativas — próximo arquivo."
        )
        return None

    for tentativa in range(1, 4):
        try: 
            with conectar() as cur:
                resultado = inserir_revisao(cur, log, revisao)
                print(f"  [INFO] Revisão de {rotulo_audio} inserida com sucesso no banco")
            break
        
        except Exception as e:
            print(
                f"  [ERRO] Falha ao salvar a revisão "
                f"'{rotulo_audio}' no banco de dados "
                f"(tentativa {tentativa}/3)"
            )
            log_dev_exc()
            if tentativa < 3:
                print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")

    else:
        print(
            f"  [ERRO] Não foi possível salvar a revisão "
            f"'{rotulo_audio}' após 3 tentativas."
        )
        return None
    
    return resultado
        

def gerar_analise_revisao(
    log: str,
    rotulo_audio: str | None = None,
    cancel: threading.Event | None = None,
) -> int | None:
    """Gera análise de IA a partir da revisão da transcrição dos áudios."""

    nome_exibicao = rotulo_audio or log

    if cancel is not None and cancel.is_set():
        print(
            f"  [CANCELADO] Análise de {nome_exibicao} não iniciada."
        )
        return None

    # Verifica se existe revisão e se a análise já foi realizada
    try:
        with conectar() as cur:

            if not verificar_coluna_revisao(cur, log):
                return None

            revisao = buscar_revisao(cur, log)

            if revisao is None:
                print(
                    f"  [AVISO] {nome_exibicao} não possui revisão "
                    f"de transcrição para analisar (pulado)"
                )
                return None

            if verificar_tabela_analise(cur, log):
                print(
                    f"  [AVISO] Análise de {nome_exibicao} já existe no banco (pulado)"
                )
                return None

    except Exception as e:
        print(
            f"  [ERRO] Falha ao verificar dados da análise "
            f"de '{rotulo_audio}' no banco"
        )
        log_dev_exc()
        return None
        
    # Análise da IA — 3 tentativas
    for tentativa in range(1, 4):
        try:
            analise_IA = analisar_ligacao(revisao)

            nota_final = analise_IA["nota_final"]
            feedback_geral = analise_IA["feedback_geral"]
            criterios = analise_IA["criterios"]
            titulo = analise_IA.get("titulo")
            resumo_chamada = analise_IA.get("resumo_chamada")
            pontos_fortes = analise_IA.get("pontos_fortes")
            fragilidades = analise_IA.get("fragilidades")
            oportunidades = analise_IA.get("oportunidades")
            break

        except Exception as e:
            print(
                f"  [ERRO] Falha ao realizar análise final "
                f"da ligação {nome_exibicao} "
                f"(tentativa {tentativa}/3)"
            )
            log_dev_exc()
            if tentativa < 3:
                print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")

    else:
        print(
            f"  [ERRO] Não foi possível realizar a análise "
            f"final de {nome_exibicao} após 3 tentativas — próximo arquivo."
        )
        return None

    # Salva a análise — 3 tentativas
    for tentativa in range(1, 4):
        try:
            with conectar() as cur:
                id_avaliacao = inserir_analise(
                    cur,
                    log,
                    nota_final,
                    feedback_geral,
                    criterios,
                    titulo=titulo,
                    resumo_chamada=resumo_chamada,
                    pontos_fortes=pontos_fortes,
                    fragilidades=fragilidades,
                    oportunidades=oportunidades,
                )

                print(f"  [INFO] Análise de {rotulo_audio} inserida com sucesso no banco")

            break

        except Exception as e:
            print(
                f"  [ERRO] Falha ao salvar a análise "
                f"'{rotulo_audio}' no banco de dados "
                f"(tentativa {tentativa}/3)"
            )
            log_dev_exc()
            if tentativa < 3:
                print(f"  [INFO] Tentando novamente ({tentativa + 1}/3) ...")

    else:
        print(
            f"  [ERRO] Não foi possível salvar a análise "
            f"'{rotulo_audio}' após 3 tentativas."
        )
        return None

    return id_avaliacao

def deletar_pasta(pasta_destino: Path, cancel: threading.Event | None = None) -> None:
    """Deleta a pasta de destino especificada e todo o seu conteúdo recursivamente."""
    if not pasta_destino.exists():
        return

    shutil.rmtree(pasta_destino, ignore_errors=True)
        
    if pasta_destino.exists():
        print(
            f"[AVISO] Não foi possível excluir a pasta temporária de trabalho."
        )
    else:
        print(
            f"[INFO] Pasta temporária de trabalho excluída com sucesso."
        )