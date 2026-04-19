"""
transcrever.py — Transcreve aula em MP4 e gera resumo de estudo via Claude API

Uso:
    python src/transcrever.py matematica/aula4.mp4
    python src/transcrever.py matematica/aula4.mp4 --modelo medium
    python src/transcrever.py matematica/aula4.mp4 --so-transcrever

Requisitos:
    pip install faster-whisper anthropic
"""

import argparse
import os
import sys
from pathlib import Path
import anthropic
from faster_whisper import WhisperModel

# ─── Configuração ───────────────────────────────────────────────
PASTA_TRANSCRICOES = Path("transcricoes")
CHAVE_API_ENV      = "ANTHROPIC_API_KEY"
MODELO_CLAUDE      = "claude-haiku-4-5-20251001"  # rápido e barato para resumos
MAX_TOKENS_RESUMO  = 4096


def carregar_chave_api():
    """Lê a chave API do ambiente ou do arquivo api_claude.txt."""
    # Tenta variável de ambiente primeiro
    chave = os.environ.get(CHAVE_API_ENV, "").strip()
    if chave:
        return chave

    # Tenta arquivo api_claude.txt na raiz do projeto
    arquivo = Path("api_claude.txt")
    if arquivo.exists():
        chave = arquivo.read_text(encoding="utf-8").strip()
        if chave.startswith("sk-ant-"):
            return chave

    print("❌ Chave API não encontrada.")
    print("   Opção 1: crie o arquivo api_claude.txt com sua chave sk-ant-...")
    print(f"   Opção 2: defina a variável de ambiente {CHAVE_API_ENV}")
    sys.exit(1)


def transcrever_audio(caminho_video: Path, modelo_whisper: str) -> tuple[str, str]:
    """
    Transcreve o áudio do vídeo com faster-whisper.
    Retorna (texto_completo, caminho_arquivo_salvo).
    """
    PASTA_TRANSCRICOES.mkdir(exist_ok=True)
    arquivo_txt = PASTA_TRANSCRICOES / (caminho_video.stem + "_transcricao.txt")

    # Reutiliza transcrição existente para não repetir o processamento
    if arquivo_txt.exists():
        print(f"✅ Transcrição já existe: {arquivo_txt}")
        print("   (apague o arquivo .txt para retranscrever)")
        return arquivo_txt.read_text(encoding="utf-8"), str(arquivo_txt)

    print(f"\n🎙️  Carregando modelo Whisper '{modelo_whisper}'...")
    print("   (primeira execução baixa o modelo — pode demorar alguns minutos)\n")

    # Usa CPU — mude para "cuda" se tiver GPU NVIDIA
    modelo = WhisperModel(modelo_whisper, device="cpu", compute_type="int8")

    print(f"⏳ Transcrevendo: {caminho_video.name}")
    print("   Isso pode levar de 15 a 45 minutos dependendo da duração da aula.\n")

    segmentos, info = modelo.transcribe(
        str(caminho_video),
        language="pt",          # força português
        beam_size=5,
        vad_filter=True,        # remove silêncios longos
        vad_parameters={"min_silence_duration_ms": 500}
    )

    print(f"   Idioma detectado: {info.language} | Duração: {info.duration:.0f}s\n")

    linhas = []
    for seg in segmentos:
        tempo = f"[{int(seg.start//60):02d}:{int(seg.start%60):02d}]"
        linhas.append(f"{tempo} {seg.text.strip()}")
        print(f"   {tempo} {seg.text.strip()}")

    texto = "\n".join(linhas)

    # Salva transcrição completa
    arquivo_txt.write_text(texto, encoding="utf-8")
    print(f"\n✅ Transcrição salva em: {arquivo_txt}")

    return texto, str(arquivo_txt)


def gerar_resumo(texto_transcricao: str, nome_aula: str, chave_api: str) -> str:
    """
    Envia a transcrição para Claude e recebe um resumo estruturado de estudo.
    """
    print("\n🤖 Gerando resumo com Claude API...")

    # Se a transcrição for muito longa, pega os primeiros 60.000 caracteres
    # (equivale a ~1h30 de aula — suficiente para um resumo completo)
    MAX_CHARS = 60_000
    if len(texto_transcricao) > MAX_CHARS:
        print(f"   ⚠️  Transcrição muito longa ({len(texto_transcricao)} chars). "
              f"Usando os primeiros {MAX_CHARS} chars.")
        texto_transcricao = texto_transcricao[:MAX_CHARS] + "\n\n[... resto da aula ...]"

    prompt = f"""Você é um professor especialista em concursos públicos brasileiros, banca CESGRANRIO.

Abaixo está a transcrição de uma aula. Crie um RESUMO DE ESTUDO completo e didático, formatado para revisão.

INSTRUÇÕES:
- Identifique o tema principal da aula
- Organize em seções com títulos claros
- Liste as REGRAS e CONCEITOS principais em tópicos curtos
- Inclua EXEMPLOS PRÁTICOS mencionados na aula
- Destaque os pontos que mais caem em prova (CESGRANRIO)
- Use linguagem simples e direta
- No final, faça um RESUMO EM ÁUDIO: frases curtas, pausas marcadas com [pausa],
  como se fosse um roteiro para ouvir no celular
- Escreva tudo em português

NOME DA AULA: {nome_aula}

TRANSCRIÇÃO:
{texto_transcricao}"""

    cliente = anthropic.Anthropic(api_key=chave_api)

    resposta = cliente.messages.create(
        model=MODELO_CLAUDE,
        max_tokens=MAX_TOKENS_RESUMO,
        messages=[{"role": "user", "content": prompt}]
    )

    return resposta.content[0].text


def salvar_resumo(resumo: str, caminho_video: Path) -> Path:
    """Salva o resumo em TXT e gera um snippet HTML para a revisao.html."""
    PASTA_TRANSCRICOES.mkdir(exist_ok=True)

    # Salva como texto puro
    arquivo_txt = PASTA_TRANSCRICOES / (caminho_video.stem + "_resumo.txt")
    arquivo_txt.write_text(resumo, encoding="utf-8")
    print(f"✅ Resumo salvo em: {arquivo_txt}")

    # Gera snippet HTML para copiar na revisao.html
    arquivo_html = PASTA_TRANSCRICOES / (caminho_video.stem + "_resumo_html.txt")
    nome_aula = caminho_video.stem.replace("_", " ").replace("-", " ").title()

    # Converte o texto em HTML básico (parágrafos e listas)
    linhas = resumo.split("\n")
    html_linhas = []
    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
        if linha.startswith("# "):
            html_linhas.append(f"<h2>{linha[2:]}</h2>")
        elif linha.startswith("## "):
            html_linhas.append(f"<h3>{linha[3:]}</h3>")
        elif linha.startswith("- ") or linha.startswith("• "):
            html_linhas.append(f"<li>{linha[2:]}</li>")
        elif linha.startswith("**") and linha.endswith("**"):
            html_linhas.append(f"<strong>{linha[2:-2]}</strong>")
        else:
            html_linhas.append(f"<p>{linha}</p>")

    snippet_html = f"""
<!-- ═══ RESUMO: {nome_aula} ═══ -->
<div class="semana-bloco" id="resumo-{caminho_video.stem}">
  <h2 class="semana-titulo">📖 {nome_aula}</h2>
  <div class="resumo-corpo">
    {''.join(html_linhas)}
  </div>
</div>
"""
    arquivo_html.write_text(snippet_html, encoding="utf-8")
    print(f"✅ Snippet HTML salvo em: {arquivo_html}")
    print("   → Copie o conteúdo desse arquivo para a revisao.html")

    return arquivo_txt


def main():
    parser = argparse.ArgumentParser(
        description="Transcreve aula MP4 e gera resumo de estudo via Claude API"
    )
    parser.add_argument(
        "video",
        help="Caminho do arquivo de vídeo (ex: matematica/aula4.mp4)"
    )
    parser.add_argument(
        "--modelo",
        default="medium",
        choices=["tiny", "base", "small", "medium", "large-v3"],
        help="Modelo Whisper (padrão: medium). Maior = mais preciso e mais lento."
    )
    parser.add_argument(
        "--so-transcrever",
        action="store_true",
        help="Apenas transcreve, sem gerar resumo com Claude"
    )
    args = parser.parse_args()

    caminho_video = Path(args.video)

    # Valida o arquivo
    if not caminho_video.exists():
        print(f"❌ Arquivo não encontrado: {caminho_video}")
        sys.exit(1)
    if not caminho_video.suffix.lower() in [".mp4", ".mp3", ".wav", ".m4a", ".mkv"]:
        print("❌ Formato não suportado. Use: mp4, mp3, wav, m4a, mkv")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  TRANSCRITOR DE AULAS — {caminho_video.name}")
    print(f"{'='*60}\n")

    # ── Passo 1: Transcrição ─────────────────────────────────────
    texto, arquivo_transcricao = transcrever_audio(caminho_video, args.modelo)
    print(f"\n📝 Transcrição: {len(texto.split())} palavras / "
          f"{len(texto)} caracteres")

    if args.so_transcrever:
        print("\n✅ Modo --so-transcrever: finalizado sem resumo.")
        print(f"   Transcrição em: {arquivo_transcricao}")
        return

    # ── Passo 2: Resumo via Claude ───────────────────────────────
    chave_api = carregar_chave_api()
    resumo = gerar_resumo(texto, caminho_video.stem, chave_api)

    # ── Passo 3: Salva resultados ────────────────────────────────
    salvar_resumo(resumo, caminho_video)

    print(f"\n{'='*60}")
    print("  CONCLUÍDO!")
    print(f"{'='*60}")
    print(f"\nArquivos gerados em: transcricoes/")
    print(f"  📄 {caminho_video.stem}_transcricao.txt  ← texto completo da aula")
    print(f"  📄 {caminho_video.stem}_resumo.txt       ← resumo de estudo")
    print(f"  📄 {caminho_video.stem}_resumo_html.txt  ← snippet para revisao.html")


if __name__ == "__main__":
    main()
