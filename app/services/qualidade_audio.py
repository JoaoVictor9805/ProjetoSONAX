import re           # Regex
import librosa      # biblioteca para análise de áudio
import soundfile    # biblioteca para leitura e escrita de arquivos de áudio
import numpy        # biblioteca para computação numérica


#==================================
# Qualidade de áudio
#==================================

def analisar_audio(caminho):
    
    # Informações técnicas do arquivo
    info = soundfile.info(caminho)

    taxa_amostragem = info.samplerate  # Quantidade de amostras por segundo (Hz)
    canais = info.channels              # Mono | Stereo
    duracao = info.duration             # Segundos

    # Carrega o áudio como mono
    audio, taxa = librosa.load(
        caminho,
        sr=None,    # Mantém a taxa de amostragem original do arquivo
        mono=True,   # Converte para mono (apenas um canal)
        duration=duracao
    )
    
    # Volume em RMS
    rms = librosa.feature.rms(y=audio)[0] # RMS calculado ao longo do tempo (em diferentes janelas do áudio)
    rms_media = float(numpy.mean(rms))    # RMS médio do áudio

    # Converte RMS para decibéis
    decibeis = librosa.amplitude_to_db(
       rms,
       ref = 1.0
    )

    # Percentual de silêncio
    silencio_limite = -40
    silencio_porcentagem = float(
        numpy.mean(decibeis < silencio_limite) * 100
    )

    # Detecta clipping
    clipping_area = numpy.sum(numpy.abs(audio) >= 0.99)

    clipping_porcentagem = (
        clipping_area / len(audio)
    ) * 100

    return {
        "duracao": round(duracao, 2),
        "taxa_amostragem": taxa_amostragem,
        "canais": canais,
        "rms": round(rms_media, 4),
        "silencio_porcentagem": round(silencio_porcentagem, 2),
        "clipping_porcentagem": round(clipping_porcentagem, 4)
    }


def classificar_qualidade_audio(dados):
    pontuacao = 100

    # Penaliza excesso de silêncio
    if dados["silencio_porcentagem"] > 90:
        pontuacao -= 70
    elif dados["silencio_porcentagem"] > 85:
        pontuacao -= 45
    elif dados["silencio_porcentagem"] > 70:
        pontuacao -= 30
    elif dados["silencio_porcentagem"] > 50:
        pontuacao -= 20
    elif dados["silencio_porcentagem"] > 30:
        pontuacao -= 10

    # Penaliza volume muito baixo
    if dados["rms"] < 0.01:
        pontuacao -= 25
    elif dados["rms"] < 0.03:
        pontuacao -= 10

    # Penaliza clipping
    if dados["clipping_porcentagem"] > 1:
        pontuacao -= 30
    elif dados["clipping_porcentagem"] > 0.1:
        pontuacao -= 15

    # Garante que a pontuação fique entre 0 e 100
    pontuacao = max(0, min(100, pontuacao))

    # Classificação em 5 níveis
    if pontuacao >= 90:
        classificacao = "Excelente"
    elif pontuacao >= 75:
        classificacao = "Bom"
    elif pontuacao >= 60:
        classificacao = "Médio"
    elif pontuacao >= 40:
        classificacao = "Ruim"
    else:
        classificacao = "Péssimo"

    return classificacao

#==================================
# Qualidade de transcrição
#==================================

def analisar_transcricao(transcricao):
    # Remove espaços extras no início e no final
    transcricao = transcricao.strip()

    # Divide a transcrição em palavras
    palavras = transcricao.split()

    # Quantidade de palavras
    quantidade_palavras = len(palavras)

    # Quantidade de caracteres
    quantidade_caracteres = len(transcricao)

    # Remove pontuação para facilitar a análise das palavras
    palavras_limpa = [
        re.sub(r"[^\wÀ-ÿ]", "", palavra.lower())
        for palavra in palavras
    ]

    # Remove palavras vazias
    palavras_limpa = [
        palavra for palavra in palavras_limpa
        if palavra
    ]

    # Conta palavras repetidas consecutivamente
    quantidade_repeticoes = 0

    for i in range(1, len(palavras_limpa)):
        if palavras_limpa[i] == palavras_limpa[i - 1]:
            quantidade_repeticoes += 1

    # Calcula a taxa de repetição
    if quantidade_palavras > 0:
        taxa_repeticao = (
            quantidade_repeticoes / quantidade_palavras
        ) * 100
    else:
        taxa_repeticao = 0

    # Conta caracteres que não são letras, números,
    # espaços ou pontuação comum
    caracteres_invalidos = len(
        re.findall(r"[^\wÀ-ÿ\s.,!?;:()\-]", transcricao)
    )

    # Retorna os indicadores encontrados
    return {
        "quantidade_palavras": quantidade_palavras,
        "quantidade_caracteres": quantidade_caracteres,
        "quantidade_repeticoes": quantidade_repeticoes,
        "taxa_repeticao": round(taxa_repeticao, 2),
        "caracteres_invalidos": caracteres_invalidos
    }


def calcular_metricas_whisper(metricas):
    if not metricas:
        return {
            "logprob_media": 0,
            "taxa_compressao_media": 0,
            "probabilidade_media_sem_fala": 0
        }

    logprob_media = sum(
        item["logprob_media"]
        for item in metricas
    ) / len(metricas)

    taxa_compressao_media = sum(
        item["taxa_compressao"]
        for item in metricas
    ) / len(metricas)

    probabilidade_media_sem_fala = sum(
        item["probabilidade_sem_fala"]
        for item in metricas
    ) / len(metricas)

    return {
        # Indica a confiança do Whisper nas escolhas feitas durante a transcrição. Quanto mais próximo de 0, maior tende a ser a confiança; valores muito negativos indicam menor confiança.
        "logprob_media": logprob_media,
        # Ajuda a identificar possíveis problemas na transcrição, como repetições anormais ou falhas na decodificação. Valores muito altos podem indicar uma transcrição problemática.
        "taxa_compressao_media": taxa_compressao_media,
        # Representa a probabilidade estimada pelo Whisper de que os segmentos não contenham fala. 
        "probabilidade_media_sem_fala": probabilidade_media_sem_fala
    }


def avaliar_qualidade_transcricao(dados):
    """
    Avalia a transcrição com base em critérios de texto e métricas do Whisper.
    Retorna um dicionário com:
        - pontuacao: int (0 a 100)
        - classificacao: str ('Excelente', 'Bom', 'Médio', 'Ruim', 'Péssimo')
        - penalizacoes: list[str] (detalhes de cada critério penalizado)
        - motivo: str (resumo formatado das penalizações)
    """
    pontuacao = 100
    penalizacoes = []

    # MÉTRICAS DO TEXTO
    # Penaliza transcrições muito curtas
    qtd_palavras = dados.get("quantidade_palavras", 0)
    if qtd_palavras < 10:
        pontuacao -= 70
        penalizacoes.append(f"Menos de 10 palavras ({qtd_palavras}) [-70]")
    elif qtd_palavras < 40:
        pontuacao -= 50
        penalizacoes.append(f"Menos de 40 palavras ({qtd_palavras}) [-50]")

    # Penaliza muitas repetições consecutivas
    taxa_rep = dados.get("taxa_repeticao", 0)
    if taxa_rep > 10:
        pontuacao -= 30
        penalizacoes.append(f"Taxa de repetição muito alta: {taxa_rep}% [-30]")
    elif taxa_rep > 5:
        pontuacao -= 15
        penalizacoes.append(f"Taxa de repetição moderada: {taxa_rep}% [-15]")

    # Penaliza caracteres inválidos
    carac_inv = dados.get("caracteres_invalidos", 0)
    if carac_inv > 5:
        pontuacao -= 20
        penalizacoes.append(f"Muitos caracteres inválidos: {carac_inv} [-20]")
    elif carac_inv > 0:
        pontuacao -= 10
        penalizacoes.append(f"Caracteres inválidos: {carac_inv} [-10]")

    # MÉTRICAS DO WHISPER
    # avg_logprob: confiança do Whisper
    logprob = dados.get("logprob_media", 0)
    if logprob < -1.0:
        pontuacao -= 30
        penalizacoes.append(f"Confiança (logprob) muito baixa: {logprob:.2f} [-30]")
    elif logprob < -0.7:
        pontuacao -= 15
        penalizacoes.append(f"Confiança (logprob) baixa: {logprob:.2f} [-15]")

    # compression_ratio: taxa de compressão
    taxa_comp = dados.get("taxa_compressao_media", 0)
    if taxa_comp > 2.4:
        pontuacao -= 25
        penalizacoes.append(f"Taxa de compressão muito alta: {taxa_comp:.2f} [-25]")
    elif taxa_comp > 2.0:
        pontuacao -= 10
        penalizacoes.append(f"Taxa de compressão alta: {taxa_comp:.2f} [-10]")

    # no_speech_prob: probabilidade de ausência de fala
    sem_fala = dados.get("probabilidade_media_sem_fala", 0)
    if sem_fala > 0.6:
        pontuacao -= 20
        penalizacoes.append(f"Alta probabilidade de silêncio/sem fala: {sem_fala:.2f} [-20]")
    elif sem_fala > 0.4:
        pontuacao -= 10
        penalizacoes.append(f"Probabilidade de silêncio moderada: {sem_fala:.2f} [-10]")

    # LIMITAÇÃO DA PONTUAÇÃO
    pontuacao = max(0, min(100, pontuacao))

    # CLASSIFICAÇÃO
    if pontuacao >= 90:
        classificacao = "Excelente"
    elif pontuacao >= 75:
        classificacao = "Bom"
    elif pontuacao >= 60:
        classificacao = "Médio"
    elif pontuacao >= 40:
        classificacao = "Ruim"
    else:
        classificacao = "Péssimo"

    return {
        "pontuacao": pontuacao,
        "classificacao": classificacao,
        "penalizacoes": penalizacoes,
        "motivo": "; ".join(penalizacoes) if penalizacoes else "Nenhuma penalização (qualidade excelente)"
    }


def classificar_qualidade_transcricao(dados):
    return avaliar_qualidade_transcricao(dados)["classificacao"]


    


if __name__ == "__main__":
    
    # ==========================================================
    # TESTE
    # ==========================================================
    
    transcricao_simulada = '''
    Bom dia, meu nome é João, estou entrando em contato
    para falar sobre o nosso serviço. Gostaria de saber
    se você possui interesse em conhecer nossa solução.
    '''

    metricas_simuladas = [
        {
            "logprob_media": -0.3,
            "taxa_compressao": 1.2,
            "probabilidade_sem_fala": 0.05
        }
    ]

    dados = {
        **analisar_transcricao(transcricao_simulada),
        **calcular_metricas_whisper(metricas_simuladas)
    }

    print("Classificação:", classificar_qualidade_transcricao(dados))
    print("Métricas:", dados)

