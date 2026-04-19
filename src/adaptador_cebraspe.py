#!/usr/bin/env python3
"""
adaptador_cebraspe.py — Converte questões CEBRASPE (certo/errado) para CESGRANRIO (A-E)

Lê um PDF CEBRASPE, extrai os itens com seus textos de apoio, e usa a Claude API
para reescrever cada grupo de itens como questões de múltipla escolha no estilo
CESGRANRIO, com gabarito, dicas e explicação completa.

Uso:
  python src/adaptador_cebraspe.py dados/provas_pdf/cebraspe_2023_petrobras_conhecimentos-basicos.pdf
  python src/adaptador_cebraspe.py --pasta dados/provas_pdf   # processa todos os CEBRASPE da pasta
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import fitz
except ImportError:
    print("❌ PyMuPDF não instalado. Execute: pip install pymupdf")
    sys.exit(1)

try:
    import anthropic
except ImportError:
    print("❌ anthropic não instalado. Execute: pip install anthropic")
    sys.exit(1)

sys.stdout.reconfigure(encoding="utf-8")

PASTA_EXTRAIDAS = Path("dados/questoes_extraidas")
PASTA_EXTRAIDAS.mkdir(parents=True, exist_ok=True)

# Disciplinas por tipo de conteúdo
MAPA_DISCIPLINAS = {
    "LÍNGUA PORTUGUESA": "Língua Portuguesa",
    "PORTUGUÊS":         "Língua Portuguesa",
    "MATEMÁTICA":        "Matemática",
    "RACIOCÍNIO LÓGICO": "Raciocínio Lógico",
    "INFORMÁTICA":       "Informática",
}


def extrair_texto_paginas(caminho):
    doc = fitz.open(str(caminho))
    return [doc[i].get_text() for i in range(doc.page_count)]


def detectar_disciplina(linha, atual):
    l = linha.upper().strip()
    if len(l) > 60:
        return atual
    for chave, valor in MAPA_DISCIPLINAS.items():
        if chave in l:
            return valor
    return atual


def extrair_blocos_cebraspe(paginas):
    """
    Extrai grupos de itens CEBRASPE, cada grupo com:
    - texto de apoio (opcional)
    - instrução ("julgue os itens...")
    - lista de itens numerados
    - disciplina
    """
    texto = "\n".join(paginas)
    linhas = texto.split("\n")

    blocos = []
    disciplina = "Língua Portuguesa"
    texto_base = []
    instrucao = ""
    itens = []

    i = 0
    while i < len(linhas):
        linha = linhas[i].strip()

        # Detecta disciplina
        nova = detectar_disciplina(linha, disciplina)
        if nova != disciplina:
            # Salva bloco atual antes de mudar de disciplina
            if itens:
                blocos.append({
                    "disciplina": disciplina,
                    "textoBase": " ".join(texto_base) if texto_base else None,
                    "instrucao": instrucao,
                    "itens": itens
                })
                texto_base = []
                instrucao = ""
                itens = []
            disciplina = nova
            i += 1
            continue

        # Detecta instrução "julgue os itens..."
        if re.search(r'julgue\s+(os|os\s+itens|os\s+próximos)', linha, re.IGNORECASE):
            # Salva bloco anterior se houver itens
            if itens:
                blocos.append({
                    "disciplina": disciplina,
                    "textoBase": " ".join(texto_base) if texto_base else None,
                    "instrucao": instrucao,
                    "itens": itens
                })
                itens = []
                texto_base = []
            instrucao = linha
            i += 1
            continue

        # Detecta item numerado (número seguido de texto substantivo)
        m = re.match(r'^(\d{1,2})\s+(.{20,})', linha)
        if m:
            itens.append({
                "num": int(m.group(1)),
                "texto": m.group(2)
            })
            i += 1
            # Continua coletando continuação do item
            while i < len(linhas):
                prox = linhas[i].strip()
                if re.match(r'^(\d{1,2})\s+.{20,}', prox):
                    break
                if re.search(r'julgue\s+os', prox, re.IGNORECASE):
                    break
                if prox and not re.match(r'^(CEBRASPE|PETROBRAS|Espaço)', prox, re.IGNORECASE):
                    itens[-1]["texto"] += " " + prox
                i += 1
            continue

        # Linhas que fazem parte do texto de apoio (antes da instrução)
        if linha and not itens and not re.match(r'^(CEBRASPE|PETROBRAS|Edital|\d{4}|PROVA)', linha, re.IGNORECASE):
            if len(linha) > 15:
                texto_base.append(linha)

        i += 1

    # Salva último bloco
    if itens:
        blocos.append({
            "disciplina": disciplina,
            "textoBase": " ".join(texto_base) if texto_base else None,
            "instrucao": instrucao,
            "itens": itens
        })

    return blocos


PROMPT_ADAPTACAO = """Você é especialista em provas de concurso público, estilo CESGRANRIO (múltipla escolha A-E).

Abaixo estão itens de uma prova CEBRASPE (formato "certo ou errado") sobre um texto de apoio.
Sua tarefa: converter CADA ITEM em uma questão de múltipla escolha independente no estilo CESGRANRIO.

REGRAS:
- Cada questão deve ter 5 alternativas (A-E), sendo apenas 1 correta
- Os distratores devem ser plausíveis mas claramente errados para quem domina o conteúdo
- Mantenha o textoBase quando a questão depender de texto de apoio
- Gere dica1 (bússola), dica2 (passo além) e explicacao completa
- Discipline e tema devem ser precisos
- Adapte o enunciado para o estilo CESGRANRIO ("Assinale a alternativa...", "É CORRETO afirmar...", etc.)

DISCIPLINA: {disciplina}

TEXTO DE APOIO (se houver):
{texto_base}

ITENS A CONVERTER:
{itens}

Retorne SOMENTE um array JSON válido, sem texto antes ou depois:
[
  {{
    "disciplina": "{disciplina}",
    "tema": "tema específico",
    "textoBase": "texto de apoio ou null",
    "enunciado": "enunciado no estilo CESGRANRIO",
    "alts": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}},
    "gabarito": "letra correta",
    "dica1": {{"area": "...", "materia": "...", "raciocinio": "bússola sem entregar a resposta"}},
    "dica2": "um passo além, aponta o método",
    "explicacao": "solução completa com justificativa de cada alternativa"
  }}
]"""


def adaptar_bloco_via_api(cliente, bloco):
    """Envia um bloco de itens para a API e retorna questões no formato CESGRANRIO."""
    itens_txt = "\n".join(
        f"{it['num']}. {it['texto']}" for it in bloco["itens"]
    )
    texto_base = bloco["textoBase"] or "(sem texto de apoio)"

    prompt = PROMPT_ADAPTACAO.format(
        disciplina=bloco["disciplina"],
        texto_base=texto_base,
        itens=itens_txt
    )

    resposta = cliente.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )

    texto = resposta.content[0].text.strip()
    # Remove markdown se houver
    texto = re.sub(r'^```(?:json)?\s*', '', texto, flags=re.MULTILINE)
    texto = re.sub(r'\s*```\s*$', '', texto, flags=re.MULTILINE)

    inicio = texto.find('[')
    fim = texto.rfind(']') + 1
    if inicio == -1 or fim == 0:
        raise ValueError("Resposta da API não contém JSON válido")

    return json.loads(texto[inicio:fim])


def processar_pdf_cebraspe(caminho, api_key):
    print(f"\n📄 {caminho.name}")

    cliente = anthropic.Anthropic(api_key=api_key)

    paginas = extrair_texto_paginas(caminho)
    blocos = extrair_blocos_cebraspe(paginas)

    print(f"   Blocos encontrados: {len(blocos)}")
    for b in blocos:
        print(f"   - {b['disciplina']}: {len(b['itens'])} itens")

    todas_questoes = []
    erros = 0

    for idx, bloco in enumerate(blocos):
        disc = bloco["disciplina"]
        n_itens = len(bloco["itens"])
        print(f"   [{idx+1}/{len(blocos)}] {disc} — {n_itens} itens → adaptando...", end=" ", flush=True)

        try:
            questoes = adaptar_bloco_via_api(cliente, bloco)
            print(f"✅ {len(questoes)} questões geradas")
            todas_questoes.extend(questoes)
        except Exception as e:
            print(f"❌ Erro: {e}")
            erros += 1

        # Pausa entre chamadas para não sobrecarregar a API
        if idx < len(blocos) - 1:
            time.sleep(1)

    print(f"\n   Total: {len(todas_questoes)} questões adaptadas ({erros} blocos com erro)")
    return todas_questoes


def salvar(questoes, nome):
    caminho = PASTA_EXTRAIDAS / f"{nome}_adaptado.json"
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(questoes, f, ensure_ascii=False, indent=2)
    print(f"   💾 {caminho}")
    return caminho


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Converte prova CEBRASPE para formato CESGRANRIO")
    parser.add_argument("arquivo", nargs="?", help="PDF CEBRASPE para adaptar")
    parser.add_argument("--pasta", help="Pasta com PDFs CEBRASPE")
    parser.add_argument("--api-key", help="Chave da API Anthropic (ou use ANTHROPIC_API_KEY no ambiente)")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        # Tenta ler do arquivo de configuração do projeto
        cfg = Path("api_claude.txt")
        if cfg.exists():
            api_key = cfg.read_text().strip()

    if not api_key:
        print("❌ Chave API não encontrada.")
        print("   Use: python src/adaptador_cebraspe.py arquivo.pdf --api-key sk-ant-...")
        print("   Ou defina a variável: set ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    if args.arquivo:
        p = Path(args.arquivo)
        if not p.exists():
            print(f"❌ Arquivo não encontrado: {p}")
            sys.exit(1)
        questoes = processar_pdf_cebraspe(p, api_key)
        nome = p.stem
        salvar(questoes, nome)

    elif args.pasta:
        pasta = Path(args.pasta)
        pdfs = list(pasta.glob("cebraspe_*.pdf"))
        if not pdfs:
            print(f"❌ Nenhum PDF com 'cebraspe_' no nome em {pasta}/")
            sys.exit(1)
        for pdf in sorted(pdfs):
            questoes = processar_pdf_cebraspe(pdf, api_key)
            salvar(questoes, pdf.stem)

    else:
        # Padrão: processa o único CEBRASPE que temos
        pdf_padrao = Path("dados/provas_pdf/cebraspe_2023_petrobras_conhecimentos-basicos.pdf")
        if pdf_padrao.exists():
            questoes = processar_pdf_cebraspe(pdf_padrao, api_key)
            salvar(questoes, pdf_padrao.stem)
        else:
            print("Uso: python src/adaptador_cebraspe.py <arquivo.pdf>")
            parser.print_help()
