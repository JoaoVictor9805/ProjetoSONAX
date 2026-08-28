# -*- coding: utf-8 -*-
"""
=======================================================================
Identifica arquivos .WAV em um diretório e copia os com mais de 1 minuto
para uma nova pasta um nível acima, nomeada como <pasta_atual>_audios_maiores_1min.

Uso:
    python script.py [DIRETORIO] [-r]

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
import sys                   # Usado para ler os argumentos passados no terminal (ex: o nome da pasta) e para encerrar o programa.# Biblioteca para acessar argumentos da linha de comando.
from pathlib import Path     # Facilita muito a manipulação de caminhos de arquivos e pastas

from .db import conectar
from .repository import (
    _parse_data,
    _parse_hora,
    _parse_timestamp,
    buscar_nome_atendente,
    inserir_registro_chamada,
)

from .transcrever import transcrever_pasta

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
        elif d > 60:
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


def parse_nome_arquivo(caminho: Path) -> dict:
    """Decompõe o nome do .wav nos 6 blocos de identificação da chamada:

        103-554130142200-26082026-113047-178775464634775-21153502152.wav
        |   |            |        |      |                 |
        |   |            |        |      |                 call_id
        |   |            |        |      timestamp_epoch   (15 dígitos, sem ponto)
        |   |            |        hora HHMMSS
        |   |            data DDMMAAAA
        |   telefone (DDI 55 + DDD + número)
        ramal / tenant

    Retorna um dict com cada campo + os blocos brutos + o stem.
    Blocos desconhecidos caem em 'extras'.
    """
    stem = caminho.stem
    blocos = [b for b in stem.split("-") if b]

    info = {
        "stem": stem,
        "blocos": blocos,
        "ramal": "",
        "telefone": "",
        "data": "",
        "hora": "",
        "timestamp": "",
        "call_id": "",
        "extras": [],
    }

    for b in blocos:
        if not b.isdigit():
            info["extras"].append(b)
            continue

        # 15 dígitos = timestamp Unix com fração (sem ponto)
        if len(b) == 15:
            info["timestamp"] = b
        # 8 dígitos = data DDMMAAAA
        elif len(b) == 8:
            info["data"] = b
        # 6 dígitos = hora HHMMSS
        elif len(b) == 6:
            info["hora"] = b
        # começa com 55 e tem >= 10 dígitos = telefone (DDI 55 + DDD + número)
        elif b.startswith("55") and len(b) >= 10:
            info["telefone"] = b
        # número grande que sobrou = call_id
        elif len(b) >= 9:
            info["call_id"] = b
        # 3-4 dígitos = ramal / tenant
        else:
            info["ramal"] = b

    return info


def parse_args(argv: list) -> tuple:
    """Lê argv e retorna (diretorio, recursivo)."""
    recursivo = "-r" in argv or "--recursive" in argv
    args = [a for a in argv if a not in ("-r", "--recursive")]
    diretorio = Path(args[0]).resolve() if args else Path.cwd()
    return diretorio, recursivo


def transcrever_dict(copiados: list) -> dict:
    """Transcreve cada arquivo copiado e devolve {path.name: texto}.
    Levanta exceção se o Whisper falhar."""
    textos = {}
    for caminho, _ in copiados:
        print(f"  [whisper] transcrevendo: {caminho.name} ...")
        from services.transcrever import transcrever_arquivo
        textos[caminho.name] = transcrever_arquivo(caminho)
    return textos


def salvar_no_banco(copiados: list) -> int:
    """Para cada arquivo copiado: transcreve, parseia o nome, busca o
    atendente pelo ramal e insere UM único registro em registro_chamadas
    com a transcrição já preenchida.

    Retorna a quantidade inserida. Pula (com aviso) se ramal não existir
    em `origem` ou se algum campo essencial estiver ausente.
    """
    transcricoes = transcrever_dict(copiados)

    inseridos = 0
    with conectar() as cur:
        for caminho, _duracao in copiados:
            info = parse_nome_arquivo(caminho)

            if not info["ramal"].isdigit():
                print(f"  [aviso] ramal inválido em {caminho.name}: "
                      f"{info['ramal']!r} — pulando")
                continue

            data = _parse_data(info["data"])
            if data is None:
                print(f"  [aviso] data inválida em {caminho.name}: "
                      f"{info['data']!r} — pulando")
                continue

            ramal = int(info["ramal"])
            nome = buscar_nome_atendente(cur, ramal)
            if nome is None:
                print(f"  [aviso] ramal {ramal} não encontrado em `origem` "
                      f"({caminho.name}) — pulando")
                continue

            texto = transcricoes.get(caminho.name, "")
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


def main():
    diretorio, recursivo = parse_args(sys.argv[1:])

    if not diretorio.is_dir():
        print(f"[ERRO] Diretório não encontrado: {diretorio}",
              file=sys.stderr)
        return 1

    wavs = sorted(
        p for p in diretorio.glob("**/*" if recursivo else "*")
        if p.is_file() and p.suffix.lower() == ".wav"
    )

    longos, curtos, invalidos = classificar_wavs(wavs)

    print(f"Diretório: {diretorio}")
    print(f"Total: {len(wavs)}   >1min: {len(longos)}   "
          f"<=1min: {len(curtos)}   inválidos: {len(invalidos)}\n")

    if not longos:
        print("Nenhum áudio com mais de 1 minuto encontrado.")
        return 0

    destino = diretorio.parent / f"{diretorio.name}_audios_maiores_1min"
    print(f"Pasta de destino: {destino}\n")

    copiados = copiar_longos_para_pasta(longos, destino)
    print(f"\n{len(copiados)} arquivo(s) copiado(s) para: {destino}")

    print("\nTranscrevendo e gravando no banco de dados...")
    try:
        inseridos = salvar_no_banco(copiados)
        print(f"\n{inseridos} registro(s) inserido(s) com transcrição.")
    except Exception as e:
        print(f"\n[ERRO BD] Falha ao gravar no banco: {e}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())