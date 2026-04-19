#!/usr/bin/env python3
"""
extrator.py — Extrai questões de PDFs de provas CESGRANRIO em lote

Uso:
  python src/extrator.py                        # processa todos os PDFs em simulados/
  python src/extrator.py simulados/prova.pdf    # processa arquivo específico
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import fitz
except ImportError:
    print("❌ PyMuPDF não instalado. Execute: pip install pymupdf")
    sys.exit(1)

sys.stdout.reconfigure(encoding="utf-8")

PASTA_PROVAS    = Path("simulados")
PASTA_EXTRAIDAS = Path("dados/questoes_extraidas")
PASTA_EXTRAIDAS.mkdir(parents=True, exist_ok=True)

# Mapa de palavras-chave de seção → nome da disciplina
MAPA_DISCIPLINAS = {
    "LÍNGUA PORTUGUESA":      "Língua Portuguesa",
    "PORTUGUÊS":              "Língua Portuguesa",
    "MATEMÁTICA":             "Matemática",
    "RACIOCÍNIO LÓGICO":      "Raciocínio Lógico",
    "RACIOCÍNIO LÓGICO-MATH": "Raciocínio Lógico",
    "INFORMÁTICA":            "Informática",
    "ELETROTÉCNICA":          "Eletrotécnica",
    "ELÉTRICA":               "Eletrotécnica",
    "MECÂNICA":               "Mecânica Industrial",
    "ELETRÔNICA":             "Eletrônica",
    "INSTRUMENTAÇÃO":         "Instrumentação",
    "CONHECIMENTOS GERAIS":   "Conhecimentos Gerais",
}


def extrair_texto_paginas(caminho):
    doc = fitz.open(str(caminho))
    return [doc[i].get_text() for i in range(doc.page_count)]


def detectar_disciplina(linha, atual):
    l = linha.upper().strip()
    if len(l) > 80:
        return atual
    for chave, valor in MAPA_DISCIPLINAS.items():
        if chave in l:
            return valor
    return atual


def proxima_linha_substantiva(linhas, pos):
    """Retorna o conteúdo da próxima linha não-vazia após pos."""
    i = pos + 1
    while i < len(linhas):
        l = linhas[i].strip()
        if l:
            return l
        i += 1
    return ""


def parece_numero_pagina(linhas, pos):
    """
    Número é de página (não questão) se:
    - A próxima linha for cabeçalho de seção, OU
    - Dentro das próximas 25 linhas não aparecer '(A)' antes de um cabeçalho de seção
    """
    # Verifica próxima linha substantiva
    prox = proxima_linha_substantiva(linhas, pos).upper()
    for chave in MAPA_DISCIPLINAS:
        if chave in prox and len(prox) < 60:
            return True

    # Lookahead: se não encontrar (A) nas próximas 25 linhas, é página
    encontrou_alt = False
    for j in range(pos + 1, min(pos + 26, len(linhas))):
        l = linhas[j].strip().upper()
        if re.match(r'^\(A\)', l):
            encontrou_alt = True
            break
        for chave in MAPA_DISCIPLINAS:
            if chave in l and len(l) < 60:
                return True  # achou seção antes de alternativa → é página
    return not encontrou_alt


def extrair_texto_base(linhas, inicio):
    """Coleta parágrafo de texto de apoio até encontrar questão ou instrução."""
    bloco = []
    i = inicio
    while i < len(linhas):
        l = linhas[i].strip()
        # Para ao encontrar número de questão ou instrução
        if re.match(r'^\d{1,2}\s*$', l):
            break
        if re.match(r'^(Questões?|Com base|Acerca|A partir|Considerando|Para (as?|os?) questões?)', l, re.IGNORECASE):
            break
        if l:
            bloco.append(l)
        i += 1
    return " ".join(bloco) if bloco else None, i


def extrair_questoes(paginas):
    texto_completo = "\n".join(paginas)
    linhas = texto_completo.split("\n")

    questoes = []
    disciplina = "Conhecimentos Gerais"
    texto_base = None

    i = 0
    while i < len(linhas):
        linha = linhas[i].strip()

        # Atualiza disciplina ao encontrar cabeçalho de seção
        nova = detectar_disciplina(linha, disciplina)
        if nova != disciplina:
            print(f"      → Seção: {nova}")
            disciplina = nova
            texto_base = None
            i += 1
            continue

        # Detecta texto de apoio ("Texto X" ou bloco antes de "Acerca do texto...")
        if re.match(r'^Texto\s+\w+', linha, re.IGNORECASE):
            texto_base, i = extrair_texto_base(linhas, i + 1)
            continue

        # Detecta início de questão: número isolado na linha
        if not re.match(r'^\d{1,2}\s*$', linha):
            i += 1
            continue

        # Descarta se for número de página (próxima linha é cabeçalho de seção)
        if parece_numero_pagina(linhas, i):
            i += 1
            continue

        num = int(linha)
        enunciado_partes = []
        alts = {}

        i += 1

        # Coleta enunciado até a primeira alternativa (A)
        while i < len(linhas):
            l = linhas[i].strip()
            if re.match(r'^\(A\)', l):
                break
            # Nova questão chegou antes de achar alternativas — descarta
            if re.match(r'^\d{1,2}\s*$', l) and not enunciado_partes:
                num = int(l)
                i += 1
                continue
            if l:
                enunciado_partes.append(l)
            i += 1

        # Coleta alternativas (A)-(E)
        alt_atual = None
        alt_partes = []
        while i < len(linhas):
            l = linhas[i].strip()
            m = re.match(r'^\(([A-E])\)\s*(.*)', l)
            if m:
                if alt_atual:
                    alts[alt_atual] = " ".join(alt_partes).strip()
                alt_atual = m.group(1)
                alt_partes = [m.group(2)] if m.group(2) else []
            elif alt_atual:
                # Linha de continuação da alternativa atual
                if re.match(r'^\d{1,2}\s*$', l) or re.match(r'^\(A\)', l):
                    break
                if l:
                    alt_partes.append(l)
            i += 1

        if alt_atual:
            alts[alt_atual] = " ".join(alt_partes).strip()

        enunciado = " ".join(enunciado_partes).strip()

        if enunciado and len(alts) >= 4:
            questoes.append({
                "num_original": num,
                "disciplina":   disciplina,
                "tema":         None,
                "textoBase":    texto_base,
                "enunciado":    enunciado,
                "alts":         alts,
                "gabarito":     None,
                "dica1":        None,
                "dica2":        None,
                "explicacao":   None
            })

    return questoes


def carregar_gabarito(caminho):
    paginas = extrair_texto_paginas(caminho)
    texto = "\n".join(paginas)
    gabarito = {}

    # Padrão: "01 – A" ou "1 - B"
    for m in re.finditer(r'\b(\d{1,2})\s*[-–]\s*([A-E])\b', texto):
        gabarito[int(m.group(1))] = m.group(2)

    # Padrão tabela: "01  A"
    if not gabarito:
        for m in re.finditer(r'\b(\d{1,2})\s+([A-E])\b', texto):
            gabarito[int(m.group(1))] = m.group(2)

    return gabarito


def encontrar_gabarito(caminho_prova):
    nome = str(caminho_prova)
    for sufixo in ["_gabarito_", "_gabarito-corrigido_"]:
        candidato = Path(nome.replace("_prova_", sufixo))
        if candidato.exists():
            return candidato
    return None


def processar_prova(caminho):
    print(f"\n📄 {caminho.name}")
    paginas = extrair_texto_paginas(caminho)
    questoes = extrair_questoes(paginas)
    print(f"   Extraídas: {len(questoes)} questões")

    gabarito_path = encontrar_gabarito(caminho)
    if gabarito_path:
        print(f"   Gabarito: {gabarito_path.name}")
        gab = carregar_gabarito(gabarito_path)
        sem_gab = 0
        for q in questoes:
            q["gabarito"] = gab.get(q["num_original"])
            if not q["gabarito"]:
                sem_gab += 1
        if sem_gab:
            print(f"   ⚠️  {sem_gab} sem gabarito")
    else:
        print("   ⚠️  Gabarito não encontrado")

    # Só retorna as que têm gabarito
    prontas = [q for q in questoes if q["gabarito"]]
    print(f"   ✅ {len(prontas)} prontas com gabarito")
    return prontas


def salvar(questoes, nome):
    caminho = PASTA_EXTRAIDAS / f"{nome}.json"
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(questoes, f, ensure_ascii=False, indent=2)
    print(f"   💾 {caminho}")
    return caminho


def processar_pasta(pasta):
    provas = sorted(pasta.glob("*_prova_*.pdf"))
    if not provas:
        print(f"❌ Nenhum PDF com '_prova_' no nome encontrado em {pasta}/")
        return

    print(f"🔍 {len(provas)} prova(s) encontrada(s)")
    total = 0
    for p in provas:
        qs = processar_prova(p)
        if qs:
            nome = p.stem.replace("_prova_", "")
            salvar(qs, nome)
            total += len(qs)

    print(f"\n✅ Total: {total} questões extraídas")
    print("   Próximo passo: python src/gerador_dicas.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extrai questões de PDFs CESGRANRIO")
    parser.add_argument("arquivo", nargs="?", help="PDF específico (opcional)")
    parser.add_argument("--pasta", default=str(PASTA_PROVAS))
    args = parser.parse_args()

    if args.arquivo:
        p = Path(args.arquivo)
        if not p.exists():
            print(f"❌ Arquivo não encontrado: {p}")
            sys.exit(1)
        qs = processar_prova(p)
        salvar(qs, p.stem.replace("_prova_", ""))
    else:
        processar_pasta(Path(args.pasta))
