#!/usr/bin/env python3
"""
injetar_aulas.py — Injeta transcrições flashcard no revisao.html

Lê os arquivos em transcricoes/*_flashcard.txt e insere como novas aulas
no array RESUMOS do revisao.html.

Uso:
  python src/injetar_aulas.py
"""
import sys
import re
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REVISAO_HTML = Path("revisao.html")
PASTA_TRANSCR = Path("transcricoes")
MARCADOR = "// ─── Adicione novas aulas aqui"

AULAS = [
    ("concordancia_flashcard",     "Concordância Nominal e Verbal", "Língua Portuguesa"),
    ("conjuncoes_flashcard",       "Conjunções do Português",        "Língua Portuguesa"),
    ("pronomes_flashcard",         "Pronomes do Português",          "Língua Portuguesa"),
    ("verbos_portugues_flashcard", "Verbos: Tempos e Modos Verbais", "Língua Portuguesa"),
    ("vozes_verbais_flashcard",    "Vozes Verbais",                  "Língua Portuguesa"),
]

html = REVISAO_HTML.read_text(encoding="utf-8")

# Verifica se já foram injetadas
if "concordancia_flashcard" in html:
    print("Aulas já injetadas anteriormente.")
    sys.exit(0)

blocos = []
for aula_id, titulo, disciplina in AULAS:
    nome_arquivo = aula_id  # ex: concordancia_flashcard
    caminho = PASTA_TRANSCR / f"{nome_arquivo}.txt"
    if not caminho.exists():
        print(f"Arquivo não encontrado: {caminho}")
        continue

    conteudo = caminho.read_text(encoding="utf-8")
    # Escapa backticks para não quebrar o template literal JS
    conteudo = conteudo.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")

    bloco = (
        f"  {{\n"
        f"    id: '{aula_id}',\n"
        f"    titulo: '{titulo} — Decoreba',\n"
        f"    disciplina: '{disciplina}',\n"
        f"    texto: `{conteudo}`\n"
        f"  }}"
    )
    blocos.append(bloco)
    print(f"OK: {aula_id}")

if not blocos:
    print("Nenhum arquivo encontrado. Rode primeiro: python src/gerar_transcricoes.py")
    sys.exit(1)

# Encontra a linha do marcador e injeta após ela
linhas = html.split("\n")
nova_linhas = []
for i, linha in enumerate(linhas):
    nova_linhas.append(linha)
    if MARCADOR in linha:
        # Injeta os blocos logo após o marcador
        for j, bloco in enumerate(blocos):
            separador = "," if j < len(blocos) - 1 else ","
            nova_linhas.append(bloco + separador)

html_novo = "\n".join(nova_linhas)
REVISAO_HTML.write_text(html_novo, encoding="utf-8")
print(f"\nOK: {len(blocos)} aulas injetadas em revisao.html")
