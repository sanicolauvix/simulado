#!/usr/bin/env python3
"""
gerar_transcricoes.py — Gera transcrições decoreba (flashcard) dos PDFs da pasta/

Formato gerado:
  [pergunta] [pausa_longa] [resposta] [pausa]

Uso:
  python src/gerar_transcricoes.py              # processa todos os PDFs em pasta/
  python src/gerar_transcricoes.py pasta/pronomes.pdf
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

try:
    import fitz
except ImportError:
    print("Instale PyMuPDF: pip install pymupdf")
    sys.exit(1)

try:
    import anthropic
except ImportError:
    print("Instale anthropic: pip install anthropic")
    sys.exit(1)

PASTA_PDFS       = Path("pasta")
PASTA_TRANSCR    = Path("transcricoes")
PASTA_TRANSCR.mkdir(exist_ok=True)


def extrair_texto(caminho):
    doc = fitz.open(str(caminho))
    return "\n".join(doc[i].get_text() for i in range(doc.page_count))


PROMPT = """Você é um professor que cria revisões em áudio no estilo DECOREBA para concursos públicos.

Abaixo está o conteúdo de um material de estudo sobre {tema}.

Sua tarefa: transformar esse conteúdo em uma sequência de FLASHCARDS FALADOS, com este formato exato:

[INTRODUÇÃO CURTA DO TEMA — 1 frase motivadora]
[pausa]

[PERGUNTA 1 — enunciado claro da regra ou conceito]
[pausa_longa]
[RESPOSTA 1 — resposta completa, direta, com exemplos se necessário]
[pausa]

[PERGUNTA 2 — próxima regra]
[pausa_longa]
[RESPOSTA 2 — resposta completa]
[pausa]

... (continue para cada regra/conceito importante do material)

[ENCERRAMENTO — frase de reforço motivador]
[pausa]

REGRAS OBRIGATÓRIAS:
- Use EXATAMENTE os marcadores [pausa] e [pausa_longa] — nunca outros formatos
- Cada PERGUNTA deve ser formulada como se o professor fosse perguntar para o aluno
  Exemplo: "Qual é a regra geral de concordância nominal?" ou "Como funciona o pronome oblíquo?"
- Cada RESPOSTA deve ser completa, clara, com exemplos curtos
- Escreva em português natural, como se estivesse falando (não use markdown, asteriscos, etc.)
- Foco nos pontos mais cobrados em concursos CESGRANRIO
- Entre 10 e 20 flashcards por arquivo (nem mais, nem menos)
- NÃO use colchetes além de [pausa] e [pausa_longa]

CONTEÚDO DO MATERIAL:
{conteudo}

Retorne SOMENTE o texto da transcrição, sem nenhuma explicação adicional."""


def gerar_transcricao(cliente, nome_arquivo, conteudo_pdf):
    tema = nome_arquivo.replace("_", " ").replace(".pdf", "").title()
    prompt = PROMPT.format(tema=tema, conteudo=conteudo_pdf[:6000])

    print(f"   Gerando flashcards para: {tema}...", end=" ", flush=True)

    resposta = cliente.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )

    texto = resposta.content[0].text.strip()
    print("OK")
    return texto


def salvar_transcricao(texto, nome_base):
    caminho = PASTA_TRANSCR / f"{nome_base}_flashcard.txt"
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)
    print(f"   Salvo em: {caminho}")
    return caminho


def processar_pdf(caminho, cliente):
    print(f"\nPDF: {caminho.name}")
    conteudo = extrair_texto(caminho)
    nome_base = caminho.stem
    transcricao = gerar_transcricao(cliente, caminho.name, conteudo)
    salvar_transcricao(transcricao, nome_base)
    return nome_base, transcricao


def carregar_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    cfg = Path("api_claude.txt")
    if cfg.exists():
        return cfg.read_text().strip()
    return None


def gerar_registro_js(nome_base, titulo, transcricao):
    """Gera o bloco JS para adicionar ao revisao.html."""
    transcricao_esc = transcricao.replace('`', r'\`').replace('${', r'\${')
    return f"""  {{
    id: '{nome_base}_flashcard',
    titulo: '{titulo} — Decoreba',
    disciplina: 'Língua Portuguesa',
    descricao: 'Flashcards para memorização. Ouça a pergunta, pause e responda em voz alta.',
    resumo: '# {titulo}\\n\\nFlashcards gerados automaticamente.\\n\\n# 🎧 RESUMO EM ÁUDIO\\n\\n{transcricao_esc}'
  }}"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gera transcrições decoreba de PDFs")
    parser.add_argument("arquivo", nargs="?", help="PDF específico (opcional)")
    args = parser.parse_args()

    api_key = carregar_api_key()
    if not api_key:
        print("Chave API não encontrada. Use: set ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    cliente = anthropic.Anthropic(api_key=api_key)

    pdfs = [Path(args.arquivo)] if args.arquivo else sorted(PASTA_PDFS.glob("*.pdf"))
    pdfs = [p for p in pdfs if "atalhos" not in p.name]  # pula atalhos_edge

    if not pdfs:
        print(f"Nenhum PDF encontrado em {PASTA_PDFS}/")
        sys.exit(1)

    print(f"Processando {len(pdfs)} PDF(s)...")
    registros = []

    for i, pdf in enumerate(pdfs):
        nome_base, transcricao = processar_pdf(pdf, cliente)
        titulo = pdf.stem.replace("_", " ").title()
        registros.append(gerar_registro_js(nome_base, titulo, transcricao))
        if i < len(pdfs) - 1:
            time.sleep(1)

    # Exibe os blocos JS para adicionar ao revisao.html
    print("\n" + "="*60)
    print("ADICIONE ESTES BLOCOS AO ARRAY 'AULAS' EM revisao.html:")
    print("="*60)
    for reg in registros:
        print(reg + ",")
        print()
